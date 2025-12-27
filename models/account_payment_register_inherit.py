import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class AccountPaymentRegisterInherit(models.TransientModel):
    _inherit = 'account.payment.register'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE (Recibo)", 
        help="Série de Facturação Electrónica para o recibo a ser criado"
    )

    @api.model
    def default_get(self, fields_list):
        res = super(AccountPaymentRegisterInherit, self).default_get(fields_list)
        if 'journal_id' in res:
            journal = self.env['account.journal'].browse(res['journal_id'])
            if journal.l10n_ao_fe_serie_id:
                res['l10n_ao_fe_serie_id'] = journal.l10n_ao_fe_serie_id.id
        return res

    @api.onchange('journal_id')
    def _onchange_journal_id_fe(self):
        if self.journal_id and self.journal_id.l10n_ao_fe_serie_id:
            self.l10n_ao_fe_serie_id = self.journal_id.l10n_ao_fe_serie_id
        else:
            self.l10n_ao_fe_serie_id = False

    def _create_payments(self):
        """Override para transferir a série FE e disparar o envio logo na criação."""
        payments = super(AccountPaymentRegisterInherit, self)._create_payments()
        
        if self.l10n_ao_fe_serie_id:
            for payment in payments:
                payment.l10n_ao_fe_serie_id = self.l10n_ao_fe_serie_id
                # No Odoo 17, se o pagamento estiver 'posted', podemos enviar logo
                if payment.state == 'posted':
                    _logger.info("FE AGT: Enviando recibo automático pós-criação: %s", payment.name)
                    try:
                        payment.action_send_fe_agt()
                    except Exception as e:
                        _logger.error("FE AGT: Erro no envio automático: %s", str(e))
        
        return payments
