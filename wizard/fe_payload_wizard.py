# -*- coding: utf-8 -*-
from odoo import models, fields, api

class FePayloadWizard(models.TransientModel):
    _name = "l10n_ao.fe.payload.wizard"
    _description = "Wizard para Visualizar Payload AGT"

    json_payload = fields.Text(string="JSON Payload", readonly=True)
    
    def action_copy(self):
        # Odoo web client handles copy to clipboard if implemented in JS, 
        # but for now this is just a placeholder or we can rely on user selecting text.
        return {'type': 'ir.actions.act_window_close'}
