# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AccountMoveReversalInherit(models.TransientModel):
    _inherit = 'account.move.reversal'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série FE (Nota de Crédito)",
        domain="[('document_class_id.code', '=', 'NC'), ('agt_status', '=', 'active')]",
        help="Selecione a série que será usada para a Nota de Crédito."
    )

    @api.model
    def default_get(self, fields_list):
        res = super(AccountMoveReversalInherit, self).default_get(fields_list)
        # Tentar preencher automaticamente uma série NC ativa
        serie_nc = self.env['l10n_ao.fe.serie'].search([
            ('document_class_id.code', '=', 'NC'),
            ('agt_status', '=', 'active')
        ], limit=1)
        if serie_nc:
            res['l10n_ao_fe_serie_id'] = serie_nc.id
        return res

    def _prepare_reverse_move_vals(self):
        vals = super(AccountMoveReversalInherit, self)._prepare_reverse_move_vals()
        if self.l10n_ao_fe_serie_id:
            vals['l10n_ao_fe_serie_id'] = self.l10n_ao_fe_serie_id.id
        return vals
