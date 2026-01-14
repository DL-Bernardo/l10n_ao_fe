# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class FeListSeriesWizard(models.TransientModel):
    _name = 'l10n_ao.fe.list.series.wizard'
    _description = 'Wizard para Listar Séries de FE da AGT'

    tax_registration_number = fields.Char(string="NIF do Emissor", required=True, default=lambda self: self.env.company.vat)
    response_json = fields.Text(string="Séries na AGT", readonly=True)

    def action_list_series(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        # Chama o serviço
        response = service.listar_series(self.tax_registration_number)
        
        # Formata a resposta
        self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.list.series.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
