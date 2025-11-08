# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FeSolicitarSerieWizard(models.TransientModel):
    _name = 'l10n_ao.fe.solicitar.serie.wizard'
    _description = 'Wizard para Solicitar Série de FE à AGT'

    serie_code = fields.Char(string="Código da Série", required=True)
    document_class_id = fields.Many2one(
        'l10n_ao.fe.document.class', 
        string="Tipo de Documento", 
        required=True
    )
    start_number = fields.Integer(string="Número Inicial", default=1, required=True)
    end_number = fields.Integer(string="Número Final", required=True)
    start_date = fields.Date(string="Data de Início", default=fields.Date.context_today, required=True)
    end_date = fields.Date(string="Data de Fim")

    def action_solicitar_serie(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        code, resp = service.solicitar_serie(
            self.serie_code,
            self.document_class_id.code,
            self.start_number,
            self.end_number,
            self.start_date,
            self.end_date
        )

        if code == 200:
            # Create the serie in Odoo
            sequence = self.env['ir.sequence'].create({
                'name': f'Série FE {self.serie_code}',
                'prefix': self.serie_code,
                'padding': 0,
            })
            self.env['l10n_ao.fe.serie'].create({
                'name': self.serie_code,
                'document_class_id': self.document_class_id.id,
                'sequence_id': sequence.id,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sucesso'),
                    'message': _('Série solicitada e criada com sucesso!'),
                    'sticky': False,
                }
            }
        else:
            service._handle_error_response(code, resp)
