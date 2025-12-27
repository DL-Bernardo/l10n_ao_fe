# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AccountPaymentRegisterInherit(models.TransientModel):
    _inherit = 'account.payment.register'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE (Recibo)", 
        help="Série de Facturação Electrónica para o recibo a ser criado"
    )

    @api.onchange('journal_id')
    def _onchange_journal_id_fe(self):
        if self.journal_id and self.journal_id.l10n_ao_fe_serie_id:
            self.l10n_ao_fe_serie_id = self.journal_id.l10n_ao_fe_serie_id

    def action_create_payments(self):
        res = super(AccountPaymentRegisterInherit, self).action_create_payments()
        
        # O resultado do action_create_payments costuma ser um dicionário de ação ou True
        # Mas os pagamentos já foram criados. No Odoo 17, os pagamentos podem ser capturados.
        # Vamos tentar disparar via hook no account.payment (action_post) para ser mais genérico.
        return res

    def _create_payments(self):
        """Override para transferir a série FE para o pagamento criado."""
        payments = super(AccountPaymentRegisterInherit, self)._create_payments()
        
        # Se foi selecionada uma série FE, atribuir ao(s) pagamento(s) criado(s)
        if self.l10n_ao_fe_serie_id:
            for payment in payments:
                payment.l10n_ao_fe_serie_id = self.l10n_ao_fe_serie_id
        
        return payments
