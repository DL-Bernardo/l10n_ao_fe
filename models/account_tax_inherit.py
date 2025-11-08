# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountTaxInherit(models.Model):
    _inherit = 'account.tax'

    l10n_ao_fe_exemption_code = fields.Char(
        string="Código de Isenção (FE AGT)",
        help="O código de isenção oficial da AGT (ex: M10, M11) a ser usado na faturação eletrónica."
    )
