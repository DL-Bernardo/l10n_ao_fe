# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AccountDebitNoteInherit(models.TransientModel):
    _inherit = 'account.debit.note'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série FE (Nota de Débito)",
        domain="[('document_class_id.code', '=', 'ND'), ('agt_status', '=', 'active')]",
        help="Selecione a série que será usada para a Nota de Débito."
    )

    @api.model
    def default_get(self, fields_list):
        res = super(AccountDebitNoteInherit, self).default_get(fields_list)
        # Tentar preencher automaticamente uma série ND ativa
        serie_nd = self.env['l10n_ao.fe.serie'].search([
            ('document_class_id.code', '=', 'ND'),
            ('agt_status', '=', 'active')
        ], limit=1)
        if serie_nd:
            res['l10n_ao_fe_serie_id'] = serie_nd.id
        return res

    def _prepare_debit_note_vals(self, move):
        vals = super(AccountDebitNoteInherit, self)._prepare_debit_note_vals(move)
        if self.l10n_ao_fe_serie_id:
            vals['l10n_ao_fe_serie_id'] = self.l10n_ao_fe_serie_id.id
        return vals
