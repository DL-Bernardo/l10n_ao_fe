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
        if not result:
            return result

        def update_dict(order_dict, record):
            order_dict['l10n_ao_fe_hash'] = record.l10n_ao_fe_hash
            qr_code = record.l10n_ao_fe_qr_code
            if qr_code and isinstance(qr_code, bytes):
                qr_code = qr_code.decode('utf-8')
            order_dict['l10n_ao_fe_qr_code'] = qr_code

        if isinstance(result, list):
            # No Odoo 17, export_for_ui em RecordSet retorna uma lista
            for order, order_dict in zip(self, result):
                update_dict(order_dict, order)
        else:
            # Caso seja um único dicionário
            update_dict(result, self)
            
        return result
