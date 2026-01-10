# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountTaxInherit(models.Model):
    _inherit = 'account.tax'

    l10n_ao_fe_tax_type = fields.Selection([
        ('IVA', 'IVA - Imposto sobre o Valor Acrescentado'),
        ('IS', 'IS - Imposto de Selo'),
        ('II', 'II - Imposto Industrial (Retenção 6.5%)'),
        ('IRT', 'IRT - Imposto sobre o Rendimento de Trabalho'),
    ], string="Tipo de Imposto (FE AGT)", default='IVA', help="Tipo de imposto conforme a tabela da AGT.")

    l10n_ao_fe_exemption_code = fields.Char(
        string="Código de Isenção (FE AGT)",
        help="O código de isenção oficial da AGT (ex: M10, M11) a ser usado na faturação eletrónica."
    )

