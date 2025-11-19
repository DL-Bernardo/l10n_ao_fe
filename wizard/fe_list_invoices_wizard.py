# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class FeListInvoicesWizard(models.TransientModel):
    _name = "l10n_ao.fe.list.invoices.wizard"
    _description = "Wizard para Listar Faturas AGT"

    date_from = fields.Date(string="Data Início", required=True)
    date_to = fields.Date(string="Data Fim", required=True)
    tax_registration_number = fields.Char(string="NIF do Emissor", required=True, default=lambda self: self.env.company.vat)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_list(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        try:
            response = service.listar_facturas(self.date_from, self.date_to, self.tax_registration_number)
            self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        except Exception as e:
            self.response_json = f"Erro: {str(e)}"
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.list.invoices.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
