# -*- coding: utf-8 -*-
from odoo import models

class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def create_invoices(self):
        # Verifica se o utilizador está a pedir um Adiantamento (fixo ou percentagem)
        if self.advance_payment_method in ['percentage', 'fixed']:
            # Injeta uma flag no contexto para que o sale.order saiba que deve usar o diário FA
            self = self.with_context(force_fa_journal=True)
                
        # Continua o processo nativo de criar faturas, mas agora com a flag no contexto
        return super(SaleAdvancePaymentInv, self).create_invoices()
