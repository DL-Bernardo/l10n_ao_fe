from odoo import models, fields, api

class FELog(models.Model):
    _name = 'l10n_ao.fe.log'
    _description = 'Log de Comunicação FE AGT'
    _order = 'timestamp desc'

    name = fields.Char(string="Endpoint", required=True)
    type = fields.Selection([
        ('request', 'Request'),
        ('response', 'Response')
    ], string="Tipo", required=True)
    
    url = fields.Char(string="URL")
    http_status = fields.Char(string="HTTP Status")
    
    payload = fields.Text(string="Payload JSON")
    response = fields.Text(string="Response JSON")
    
    timestamp = fields.Datetime(string="Timestamp", default=fields.Datetime.now)
    
    move_id = fields.Many2one('account.move', string="Fatura Relacionada")
    request_id = fields.Char(string="Request ID (AGT)")
    
    def name_get(self):
        result = []
        for log in self:
            name = f"{log.timestamp} - {log.name} ({log.type})"
            result.append((log.id, name))
        return result
