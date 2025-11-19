# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class FeGetStateWizard(models.TransientModel):
    _name = "l10n_ao.fe.get.state.wizard"
    _description = "Wizard para Obter Estado AGT"

    request_id = fields.Char(string="Request ID", required=True)
    tax_registration_number = fields.Char(string="NIF do Emissor", required=True, default=lambda self: self.env.company.vat)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_get_state(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        # Chama o serviço
        response = service.obter_estado(self.request_id, self.tax_registration_number)
        
        # Formata a resposta
        self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.get.state.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
