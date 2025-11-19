# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class FeConsultInvoiceWizard(models.TransientModel):
    _name = "l10n_ao.fe.consult.invoice.wizard"
    _description = "Wizard para Consultar Fatura AGT"

    document_no = fields.Char(string="Número do Documento", required=True)
    tax_registration_number = fields.Char(string="NIF do Emissor", required=True, default=lambda self: self.env.company.vat)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_consult(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        try:
            response = service.consultar_factura(self.document_no, self.tax_registration_number)
            self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        except Exception as e:
            self.response_json = f"Erro: {str(e)}"
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.consult.invoice.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
