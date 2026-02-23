# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de Facturas",
        domain="[('is_ft', '=', True), ('agt_status', '=', 'active')]",
        help="Série da AGT usada para Facturas (FT) neste diário."
    )

    l10n_ao_fe_refund_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de Notas de Crédito",
        domain="[('is_nc', '=', True), ('agt_status', '=', 'active')]",
        help="Série da AGT usada para Notas de Crédito (NC) neste diário."
    )

    l10n_ao_fe_debit_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de Notas de Débito",
        domain="[('is_nd', '=', True), ('agt_status', '=', 'active')]",
        help="Série da AGT usada para Notas de Débito (ND) neste diário."
    )

class IrSequenceInherit(models.Model):
    _inherit = 'ir.sequence'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie',
        string="Série FE (AGT)",
        help="Vincula esta sequência Odoo a uma série autorizada da AGT."
    )

    @api.onchange('l10n_ao_fe_serie_id')
    def _onchange_l10n_ao_fe_serie_id(self):
        if self.l10n_ao_fe_serie_id:
            # Formata o prefixo conforme padrão AGT: TIPO SERIE/
            # Ex: FT S2025/
            doc_type = self.l10n_ao_fe_serie_id.document_class_id.code or 'FT'
            serie_name = self.l10n_ao_fe_serie_id.name
            self.prefix = f"{doc_type} {serie_name}/"
            self.padding = 3 # Ex: 001, 002...
            self.number_next_actual = self.l10n_ao_fe_serie_id.next_number or 1
