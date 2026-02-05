# -*- coding: utf-8 -*-
from odoo import models

class PosSessionInherit(models.Model):
    _inherit = 'pos.session'

    def _loader_params_pos_order(self):
        params = super()._loader_params_pos_order()
        params['search_params']['fields'].extend([
            'l10n_ao_fe_hash',
            'l10n_ao_fe_qr_code',
            'l10n_ao_fe_status'
        ])
        return params
