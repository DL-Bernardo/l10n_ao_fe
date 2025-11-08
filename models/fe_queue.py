from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class FEQueue(models.Model):
    _name = 'l10n_ao.fe.queue'
    _description = 'Fila de envio de facturas FE'
    _order = 'create_date desc'

    invoice_id = fields.Many2one('account.move', string='Fatura', readonly=True)
    state = fields.Selection([
        ('draft', 'Rascunho'),
        ('processing', 'Em processamento'),
        ('done', 'Concluída'),
        ('error', 'Erro'),
    ], default='draft', string="Estado")
    payload = fields.Json(string='Payload', readonly=True)
    request_id = fields.Char(string='Request ID', readonly=True)
    last_response = fields.Text(string='Última Resposta', readonly=True)
    attempts = fields.Integer(default=0, string="Tentativas")
    error_list = fields.Text(string='Erros', readonly=True)

    def action_send(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        company = self.invoice_id.company_id
        documents = [self.payload]

        code, resp = service.registar_facturas(company, documents)

        self.attempts += 1
        self.last_response = str(resp)

        if code in (200, 202) and resp.get('requestID'):
            self.write({
                'request_id': resp['requestID'],
                'state': 'processing',
                'error_list': False,
            })
        else:
            self.state = 'error'
            self.error_list = str(resp.get('errorList') or resp)

    def action_obter_estado(self):
        self.ensure_one()
        if not self.request_id:
            return
        service = self.env['l10n_ao.fe.service']
        code, resp = service.obter_estado(self.request_id, self.invoice_id.company_id)
        self.last_response = str(resp)

        result_code = resp.get('resultCode')
        if code == 200 and result_code in ('0', '1', '2'):
            doc_status = resp.get('documentStatusList', [])[0]
            final_status = doc_status.get('documentStatus')
            self.invoice_id.fe_status = final_status
            if final_status == 'I':
                errors = doc_status.get('errorList', [])
                self.error_list = "\n".join([f"{e['idError']}: {e['descriptionError']}" for e in errors])
                self.invoice_id.message_post(body=f"Fatura inválida pela AGT.\nErros:\n{self.error_list}")
                self.state = 'error'
            else:
                self.invoice_id.message_post(body="Fatura validada com sucesso pela AGT.")
                self.state = 'done'
        elif result_code in ('8',): # Ainda em processamento
            _logger.info(f"Fatura {self.invoice_id.name} ainda em processamento.")
        else: # Erro
            self.state = 'error'
            self.error_list = str(resp.get('requestErrorList') or resp)

    @api.model
    def _process_queue(self):
        _logger.info("A processar a fila de faturas da AGT...")
        # Enviar faturas pendentes
        pending_records = self.search([('state', '=', 'draft'), ('attempts', '<', 3)], limit=10)
        for rec in pending_records:
            try:
                rec.action_send()
                self.env.cr.commit()
            except Exception as e:
                _logger.error(f"Erro ao enviar fatura {rec.invoice_id.name}: {e}")
                rec.write({'state': 'error', 'error_list': str(e)})
                self.env.cr.commit()

        # Verificar estado de faturas em processamento
        processing_records = self.search([('state', '=', 'processing')], limit=20)
        for rec in processing_records:
            try:
                rec.action_obter_estado()
                self.env.cr.commit()
            except Exception as e:
                _logger.error(f"Erro ao obter estado da fatura {rec.invoice_id.name}: {e}")
                rec.write({'state': 'error', 'error_list': str(e)})
                self.env.cr.commit()
        _logger.info("Processamento da fila de faturas da AGT concluído.")