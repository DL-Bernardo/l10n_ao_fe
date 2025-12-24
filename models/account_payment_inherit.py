# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)

class AccountPaymentInherit(models.Model):
    _inherit = 'account.payment'

    fe_request_id = fields.Char(string='AGT Request ID', readonly=True, copy=False)
    fe_submission_uuid = fields.Char(string="AGT Submission UUID", copy=False, readonly=True)
    
    fe_status = fields.Selection([
        ('not_sent', 'Não Enviado'),
        ('processing', 'Em Processamento'),
        ('sent', 'Enviado'),
        ('validated', 'Validado'),
        ('error', 'Erro'),
        ('cancelled', 'Anulado')
    ], string="Estado FE", default='not_sent', copy=False, tracking=True)

    fe_last_response = fields.Text(string="Última resposta AGT", copy=False, readonly=True)
    fe_payload_json = fields.Text(string="Último Payload JSON", copy=False, readonly=True)
    fe_document_hash = fields.Char(string="Hash AGT", copy=False, readonly=True)
    
    fe_jws_document_signature = fields.Text(string="JWS Document Signature", copy=False, readonly=True)
    fe_jws_software_signature = fields.Text(string="JWS Software Signature", copy=False, readonly=True)
    
    fe_sent_datetime = fields.Datetime(string="Data de Submissão AGT", copy=False, readonly=True)
    fe_error_list = fields.Text(string="Lista de Erros", copy=False, readonly=True)

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE", 
        readonly=True, 
        copy=False
    )

    def action_send_fe_agt(self):
        """Gera o payload, envia para AGT e processa a resposta."""
        service = self.env['l10n_ao.fe.service'].with_context(force_company=self.company_id.id)
        
        for payment in self:
            if payment.state != 'posted':
                raise UserError(_("Apenas pagamentos no estado 'Lançado' podem ser enviados à AGT."))
            
            payment.write({'fe_status': 'processing'})
            
            try:
                response = service.registar_recibo(payment)
                
                request_id = response.get("requestID")
                # Emissão autorizada imediata ou diferida?
                # Para recibos, o status costuma estar no documents[0].documentStatus se for sincrono,
                # mas geralmente é assincrono via requestID.
                
                vals = {
                    'fe_request_id': request_id,
                    'fe_status': 'sent' if request_id else 'error',
                    'fe_last_response': json.dumps(response, indent=2, ensure_ascii=False)
                }
                
                # Se a AGT devolver erro na resposta imediata
                error_list = response.get('errorList', [])
                real_errors = [e for e in error_list if isinstance(e, dict) and (e.get('idError') or e.get('errorCode'))]
                
                if real_errors:
                    vals['fe_status'] = 'error'
                    error_msgs = "\n".join([f"({e.get('idError', e.get('errorCode'))}) {e.get('descriptionError', e.get('errorDescription'))}" for e in real_errors])
                    vals['fe_error_list'] = error_msgs or str(error_list)
                
                payment.write(vals)
                
                if hasattr(payment, 'message_post'):
                    msg = _("Recibo enviado para a AGT. Request ID: %s", request_id)
                    if vals['fe_status'] == 'error':
                        msg = _("Erro no envio do recibo: %s", vals.get('fe_error_list'))
                    payment.message_post(body=msg)
                
            except Exception as e:
                payment.write({
                    'fe_status': 'error',
                    'fe_error_list': str(e)
                })
                if hasattr(payment, 'message_post'):
                    payment.message_post(body=_("Erro ao enviar recibo para AGT: %s", str(e)))

    def open_payload_wizard(self):
        """Abre o wizard para mostrar o payload JSON."""
        self.ensure_one()
        
        # Regenerar payload se não estiver validado, para refletir correções de código
        if self.fe_status != 'success':
            try:
                # Chama o serviço para gerar o JSON atualizado
                payload = self.env['l10n_ao.fe.service'].registar_recibo(self, preview=True)
            except Exception as e:
                payload = f"Erro ao gerar preview: {str(e)}"
        else:
            payload = self.fe_payload_json or "Payload não disponível."

        return {
            'name': _('Payload JSON'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.payload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_json_payload': payload}
        }

    def open_obter_estado_wizard(self):
        self.ensure_one()
        return {
            'name': _('Obter Estado AGT'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.get.state.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.fe_request_id,
                'default_tax_registration_number': self.company_id.vat
            }
        }
