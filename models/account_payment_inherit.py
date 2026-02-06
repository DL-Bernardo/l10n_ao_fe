import logging
import json
import base64
import qrcode
from io import BytesIO
from qrcode.constants import ERROR_CORRECT_M
from PIL import Image
import os
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

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
    fe_qr_code = fields.Binary(string="QR Code AGT", copy=False, readonly=True)

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE", 
        readonly=True, 
        copy=False
    )

    def action_post(self):
        res = super(AccountPaymentInherit, self).action_post()
        
        for payment in self:
            if payment.payment_type == 'inbound' and payment.l10n_ao_fe_serie_id:
                _logger.info("FE AGT: Disparando envio automático para o recibo %s", payment.name)
                try:
                    payment.action_send_fe_agt()
                except Exception as e:
                    _logger.error("FE AGT: Erro no envio automático do recibo: %s", str(e))
        
        return res

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

                # Se for validado imediatamente
                doc_status = response.get('documents', [{}])[0].get('documentStatus') if response.get('documents') else False
                if doc_status == 'V':
                    payment.write({'fe_status': 'validated'})
                    payment.generate_qr_code()
                
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

    def generate_qr_code(self):
        """Gera QR Code para o recibo conforme especificações actualizadas da AGT (Novo URL 2026)"""
        # Novo URL Oficial (AGT): https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_ao_fe.qrcode_base_url', 
            "https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe"
        )

        for payment in self:
            if not payment.name:
                continue

            # NIF do Emissor (Remover prefixo de país)
            nif_emissor = payment.company_id.vat or ""
            if nif_emissor.startswith('AO'):
                nif_emissor = nif_emissor[2:]
            
            # Número do documento
            # Garantir formato Tipo + Espaço + Numero (Ex: RC RC...)
            doc_type = payment.l10n_ao_fe_serie_id.document_class_id.code or "RC"
            document_no = payment.name
            if not document_no.startswith(f"{doc_type} "):
                document_no = f"{doc_type} {document_no}"
            
            document_no_encoded = document_no.replace(" ", "%20")
            
            # Montar URL final
            qr_url = f"{base_url}?emissor={nif_emissor}&document={document_no_encoded}"

            qr = qrcode.QRCode(
                version=4, # Versão 4
                error_correction=ERROR_CORRECT_M, # Nível M
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            # Adicionar logotipo da AGT
            try:
                logo_full_path = file_path('l10n_ao_fe/static/description/agt_logo.png')
                if os.path.exists(logo_full_path):
                    logo = Image.open(logo_full_path).convert('RGBA')
                    qr_width, qr_height = qr_img.size
                    logo_size = int(qr_width * 0.20)
                    logo.thumbnail((logo_size, logo_size))
                    pos = ((qr_width - logo.width) // 2, (qr_height - logo.height) // 2)
                    qr_img.paste(logo, pos, logo)
            except Exception as e:
                _logger.warning("Não foi possível adicionar o logotipo ao QR Code do recibo: %s", e)

            # Redimensionar para 350x350
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            qr_img = qr_img.resize((350, 350), resample)

            # Converter para base64
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            payment.fe_qr_code = base64.b64encode(buf.getvalue())
            buf.close()

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
