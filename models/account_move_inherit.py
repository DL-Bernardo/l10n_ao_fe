# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.modules.module import get_module_resource
from datetime import datetime
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from io import BytesIO
import base64
from PIL import Image
import os
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    fe_request_id = fields.Char(string='AGT Request ID', readonly=True, copy=False, tracking=True)
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

    fe_qr_code = fields.Binary(string="QR Code AGT", readonly=True, copy=False)
    
    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE", 
        readonly=True, 
        states={'draft': [('readonly', False)]},
        copy=False
    )
    l10n_ao_fe_document_class_id = fields.Many2one(
        'l10n_ao.fe.document.class', 
        string="Tipo de Documento FE",
        related='l10n_ao_fe_serie_id.document_class_id',
        store=True
    )
    l10n_ao_fe_queue_ids = fields.One2many('l10n_ao.fe.queue', 'invoice_id', string='Fila de Envio AGT')

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        # Logic to auto-select series based on journal can be added here
        pass

    def _get_document_number_for_fe(self):
        """Constructs the document number based on the selected series or falls back to the invoice name."""
        self.ensure_one()
        if self.l10n_ao_fe_serie_id and self.l10n_ao_fe_serie_id.sequence_id:
            # This logic might need adjustment depending on how sequences are configured.
            # Assuming the name is already correctly set by the sequence.
            return self.name
        return self.name

    def action_send_fe_agt(self):
        """Gera o payload, envia para AGT e processa a resposta."""
        service = self.env['l10n_ao.fe.service'].with_context(force_company=self.company_id.id)
        
        for move in self:
            if move.state != 'posted':
                raise UserError(_("Apenas faturas no estado 'Lançado' podem ser enviadas à AGT."))
            
            move.write({'fe_status': 'processing'})
            move.message_post(body=_("A preparar e enviar para a AGT..."))

            try:
                # O método registar_factura do serviço já faz tudo: gera payload, assina, envia e loga.
                response = service.registar_factura(move)
                
                # Processar resposta imediata
                request_id = response.get("requestID")
                doc_status_info = response.get('documents', [{}])[0]
                doc_status = doc_status_info.get('documentStatus', 'processing')
                error_list = doc_status_info.get('errorList', [])

                # Status mapping based on AGT spec
                # V = Valid, I = Invalid, N = Received/Normal?
                # If we get a requestID, it's usually 'sent' or 'processing' until validated.
                
                final_status = 'sent'
                if doc_status == 'V':
                    final_status = 'validated'
                    move.generate_qr_code()
                elif doc_status == 'I' or error_list:
                    final_status = 'error'
                    error_msgs = "\n".join([f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list])
                    move.fe_error_list = error_msgs
                
                move.write({
                    'fe_request_id': request_id,
                    'fe_status': final_status,
                    'fe_last_response': json.dumps(response, indent=2, ensure_ascii=False)
                })

                msg = _("Enviado para a AGT.<br/>- Request ID: %s<br/>- Estado: %s", request_id, final_status)
                move.message_post(body=msg)

            except Exception as e:
                move.write({'fe_status': 'error'})
                move.message_post(body=_("<b>Falha ao enviar para AGT:</b> %s", str(e)))
                # Não faz raise para não bloquear a UI, mas loga o erro no chatter

    def action_download_fe(self):
        """Gera e descarrega o PDF da Fatura Electrónica."""
        # Lógica para gerar PDF específico ou usar o report padrão com QR Code
        # Por agora, retorna o report padrão
        return self.env.ref('account.account_invoices').report_action(self)

    def open_payload_wizard(self):
        """Abre o wizard para mostrar o payload JSON."""
        self.ensure_one()
        # Regenerar payload se não estiver validado, para refletir correções de código
        if self.fe_status != 'success':
            try:
                # Chama o serviço para gerar o JSON atualizado
                payload = self.env['l10n_ao.fe.service'].registar_factura(self, preview=True)
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

    def open_consultar_factura_wizard(self):
        self.ensure_one()
        return {
            'name': _('Consultar Fatura AGT'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.consult.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_no': self.name,
                'default_tax_registration_number': self.company_id.vat
            }
        }

    def open_listar_facturas_wizard(self):
        return {
            'name': _('Listar Faturas AGT'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.list.invoices.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tax_registration_number': self.env.company.vat
            }
        }

    def action_cancel_fe(self):
        """Anula a fatura na AGT (se suportado) e localmente."""
        # Implementar lógica de anulação AGT se houver endpoint específico ou processo
        self.write({'fe_status': 'cancelled'})
        return self.button_cancel()

    # =====================================================
    # MÉTODO PARA GERAR O QR CODE (PADRÃO AGT)
    # =====================================================
    def generate_qr_code(self):
        """Gera QR Code conforme especificações da AGT"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('l10n_ao_fe.qrcode_base_url', "https://portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo=")

        for inv in self:
            if not inv.name:
                continue

            document_no = inv._get_document_number_for_fe().replace(" ", "%20")
            qr_url = f"{base_url}{document_no}"

            qr = qrcode.QRCode(
                version=4,
                error_correction=ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            # Adicionar logotipo da AGT ao centro
            logo_path = get_module_resource('l10n_ao_fe', 'static', 'description', 'agt_logo.png')
            if logo_path and os.path.exists(logo_path):
                try:
                    logo = Image.open(logo_path)
                    qr_width, qr_height = qr_img.size

                    # Redimensionar logo (20% do QR)
                    logo_size = int(qr_width * 0.20)
                    logo.thumbnail((logo_size, logo_size))
                    pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                    qr_img.paste(logo, pos, logo) # Use logo as mask for transparency

                except Exception as e:
                    _logger.warning("Não foi possível adicionar o logotipo ao QR Code: %s", e)

            # Redimensionar para 350x350 px
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            qr_img = qr_img.resize((350, 350), resample)

            # Converter imagem para base64 e guardar na fatura
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            inv.fe_qr_code = base64.b64encode(buf.getvalue())
            buf.close()
