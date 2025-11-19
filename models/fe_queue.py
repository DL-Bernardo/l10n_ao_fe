# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
import json

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
        
        try:
            # O serviço agora espera um account.move
            response = service.registar_factura(self.invoice_id)
            
            request_id = response.get("requestID")
            doc_status_info = response.get('documents', [{}])[0]
            doc_status = doc_status_info.get('documentStatus', 'processing')
            
            self.attempts += 1
            self.last_response = json.dumps(response, indent=2, ensure_ascii=False)
            self.request_id = request_id
            
            if doc_status == 'I':
                 error_list = doc_status_info.get('errorList', [])
                 self.state = 'error'
                 self.error_list = "\n".join([f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list])
            else:
                 self.state = 'processing'
                 self.error_list = False

        except Exception as e:
            self.state = 'error'
            self.error_list = str(e)

    def action_obter_estado(self):
        self.ensure_one()
        if not self.request_id:
            return
        
        service = self.env['l10n_ao.fe.service']
        try:
            response = service.obter_estado(self.request_id, self.invoice_id.company_id.vat)
            self.last_response = json.dumps(response, indent=2, ensure_ascii=False)
            
            status_info = response.get('statusInfo', {})
            agt_status_code = status_info.get('statusCode')
            
            if agt_status_code == 'V':
                self.state = 'done'
                self.invoice_id.fe_status = 'validated'
                self.invoice_id.generate_qr_code()
            elif agt_status_code == 'I':
                self.state = 'error'
                self.invoice_id.fe_status = 'error'
                # Extrair erros se houver
            
        except Exception as e:
            self.state = 'error'
            self.error_list = str(e)

    @api.model
    def _process_queue(self):
        _logger.info("A processar a fila de faturas da AGT...")
        # Enviar faturas pendentes (Rascunho ou Erro com < 3 tentativas)
        pending_records = self.search([('state', 'in', ['draft', 'error']), ('attempts', '<', 3)], limit=10)
        for rec in pending_records:
            try:
                rec.action_send()
                self.env.cr.commit()
            except Exception as e:
                _logger.error(f"Erro ao enviar fatura {rec.invoice_id.name}: {e}")
                self.env.cr.commit()

        # Verificar estado de faturas em processamento
        processing_records = self.search([('state', '=', 'processing')], limit=20)
        for rec in processing_records:
            try:
                rec.action_obter_estado()
                self.env.cr.commit()
            except Exception as e:
                _logger.error(f"Erro ao obter estado da fatura {rec.invoice_id.name}: {e}")
                self.env.cr.commit()
        _logger.info("Processamento da fila de faturas da AGT concluído.")