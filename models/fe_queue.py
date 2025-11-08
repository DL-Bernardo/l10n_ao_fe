from odoo import models, fields, api

class FEQueue(models.Model):
    _name = 'l10n_ao.fe.queue'
    _description = 'Fila de envio de facturas FE'

    invoice_id = fields.Many2one('account.move', string='Fatura')
    state = fields.Selection([
        ('draft', 'Rascunho'),
        ('sent', 'Enviada'),
        ('processing', 'Em processamento'),
        ('done', 'Concluída'),
        ('error', 'Erro'),
    ], default='draft')
    payload = fields.Json(string='Payload')
    request_id = fields.Char(string='Request ID')
    last_response = fields.Text(string='Última Resposta')
    attempts = fields.Integer(default=0)
    error_list = fields.Text(string='Erros')

    def action_send(self):
        service = self.env['l10n_ao.fe.service']
        company = self.invoice_id.company_id
        documents = [self.payload]
        code, resp = service.registar_facturas(company, documents)
        self.attempts += 1
        self.last_response = str(resp)
        if code == 200 and isinstance(resp, dict):
            self.request_id = resp.get('requestId')
            self.state = 'processing' if self.request_id else 'error'
        else:
            self.state = 'error'
            self.error_list = str(resp)

    def action_obter_estado(self):
        if not self.request_id:
            return
        service = self.env['l10n_ao.fe.service']
        code, resp = service.obter_estado(self.request_id)
        self.last_response = str(resp)
        if code == 200 and resp.get('status') == 'SUCCESS':
            self.state = 'done'
        elif code == 200 and resp.get('status') == 'ERROR':
            self.state = 'error'
        else:
            self.state = 'processing'