import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class AccountPaymentRegisterInherit(models.TransientModel):
    _inherit = 'account.payment.register'

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE (Recibo)", 
        compute='_compute_l10n_ao_fe_serie_id',
        store=True, readonly=False, precompute=True,
        help="Série de Facturação Electrónica para o recibo a ser criado"
    )

    @api.depends('journal_id')
    def _compute_l10n_ao_fe_serie_id(self):
        for wizard in self:
            if wizard.journal_id and wizard.journal_id.l10n_ao_fe_serie_id:
                wizard.l10n_ao_fe_serie_id = wizard.journal_id.l10n_ao_fe_serie_id
            else:
                # Tentar encontrar a primeira série RG ou RC ativa se o diário não tiver uma predefinida
                serie = self.env['l10n_ao.fe.serie'].search([
                    ('document_class_id.code', 'in', ['RG', 'RC']),
                    ('agt_status', '=', 'active')
                ], limit=1)
                wizard.l10n_ao_fe_serie_id = serie.id if serie else False

    @api.model
    def default_get(self, fields_list):
        res = super(AccountPaymentRegisterInherit, self).default_get(fields_list)
        # Reforço extra no default_get para garantir o ID no carregamento
        if 'journal_id' in res and not res.get('l10n_ao_fe_serie_id'):
            journal = self.env['account.journal'].browse(res['journal_id'])
            if journal.l10n_ao_fe_serie_id:
                res['l10n_ao_fe_serie_id'] = journal.l10n_ao_fe_serie_id.id
        return res

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
