# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrderInherit(models.Model):
    _inherit = 'pos.order'

    l10n_ao_fe_hash = fields.Char(related='account_move.fe_document_hash', string="Hash AGT (POS)")
    l10n_ao_fe_qr_code = fields.Binary(related='account_move.fe_qr_code', string="QR Code AGT (POS)")
    l10n_ao_fe_status = fields.Selection(related='account_move.fe_status', string="Estado FE (POS)")

    def _prepare_invoice_vals(self):
        vals = super(PosOrderInherit, self)._prepare_invoice_vals()
        
        # Identificar como factura vinda do POS
        vals['is_pos_invoice'] = True
        
        # Para a AGT, faturas do POS são Factura-Recibo (FR) porque são pagas na hora
        # 1. Tentar encontrar o diário FR padrão do módulo de certificação
        journal_fr = self.env.ref('opc_certification_ao_v17.opc_journal_fr', raise_if_not_found=False)
        
        # 2. Se não encontrou pelo XML ID, procurar por saft_inv_type
        if not journal_fr:
            journal_fr = self.env['account.journal'].search([
                ('saft_inv_type', '=', 'FR'),
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if journal_fr:
            vals['journal_id'] = journal_fr.id
            # No Odoo 17, a série FE pode estar no diário ou ser buscada via document_class
            if hasattr(journal_fr, 'l10n_ao_fe_serie_id') and journal_fr.l10n_ao_fe_serie_id:
                vals['l10n_ao_fe_serie_id'] = journal_fr.l10n_ao_fe_serie_id.id
        
        # 2. Se não encontrou no diário, tenta procurar uma série FR activa independente
        if not vals.get('l10n_ao_fe_serie_id'):
            serie_fr = self.env['l10n_ao.fe.serie'].search([
                ('document_class_id.code', '=', 'FR'),
                ('agt_status', '=', 'active'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if serie_fr:
                vals['l10n_ao_fe_serie_id'] = serie_fr.id
            
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
