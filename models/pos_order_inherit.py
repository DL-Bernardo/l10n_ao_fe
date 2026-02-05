# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrderInherit(models.Model):
    _inherit = 'pos.order'

    l10n_ao_fe_hash = fields.Char(related='account_move.fe_document_hash', string="Hash AGT (POS)")
    l10n_ao_fe_qr_code = fields.Binary(related='account_move.fe_qr_code', string="QR Code AGT (POS)")
    l10n_ao_fe_status = fields.Selection(related='account_move.fe_status', string="Estado FE (POS)")

    def _prepare_invoice_vals(self):
        vals = super(PosOrderInherit, self)._prepare_invoice_vals()
        return vals

    def export_for_ui(self):
        result = super(PosOrderInherit, self).export_for_ui()
        result['l10n_ao_fe_hash'] = self.l10n_ao_fe_hash
        result['l10n_ao_fe_qr_code'] = self.l10n_ao_fe_qr_code.decode('utf-8') if self.l10n_ao_fe_qr_code else None
        return result
