# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE por Defeito",
        help="Série da AGT que será selecionada automaticamente ao usar este diário."
    )
