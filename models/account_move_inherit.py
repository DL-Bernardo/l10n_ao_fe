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

    fe_request_id = fields.Char(string='FE Request ID', readonly=True, copy=False, tracking=True)
    fe_status = fields.Selection([
        ('not_sent', 'Não Enviada'),
        ('processing', 'Em Processamento'),
        ('v', 'Válida'),
        ('i', 'Inválida')
    ], string="Estado AGT", default='not_sent', readonly=True, copy=False, tracking=True)
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
    l10n_ao_fe_queue_ids = fields.One2many('l10n_ao.fe.queue', 'invoice_id', string='Fila de Envio AGT (Legado)')
    l10n_ao_fe_payload_json = fields.Text(string="Payload JSON Enviado", readonly=True, copy=False)

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

    def action_post(self):
        """Assigns the sequence number upon validation."""
        # The logic to set the name from the sequence should be handled by Odoo's standard mechanisms
        # or a more specific module if custom logic is needed before posting.
        return super(AccountMoveInherit, self).action_post()

    def action_send_fe(self):
        """Generates the payload, sends it directly to AGT, and handles the response."""
        service = self.env['l10n_ao.fe.service'].with_context(force_company=self.company_id.id)
        
        for move in self:
            if move.state != 'posted':
                raise UserError(_("Apenas faturas no estado 'Lançado' podem ser enviadas à AGT."))
            
            # if not move.l10n_ao_fe_serie_id:
            #     raise UserError(_("Por favor, selecione uma 'Série de FE' para este documento antes de o enviar."))

            move.write({'fe_status': 'processing'})
            move.message_post(body=_("A preparar e enviar para a AGT..."))

            try:
                # 1. Gerar o payload
                payload_json = service._generate_invoice_payload(move)
                move.l10n_ao_fe_payload_json = payload_json

                # 2. Enviar para a AGT
                response = service._send_to_agt(payload_json)
                
                # 3. Processar a resposta
                request_id = response.get("requestID")
                doc_status_info = response.get('documents', [{}])[0]
                doc_status = doc_status_info.get('documentStatus', 'processing')
                
                status_mapping = {'V': 'v', 'I': 'i'}
                final_status = status_mapping.get(doc_status, 'processing')

                move.write({
                    'fe_request_id': request_id,
                    'fe_status': final_status,
                })

                msg = _("Enviado com sucesso para a AGT.<br/>- Request ID: %s<br/>- Estado do Documento: %s", request_id, final_status)
                if final_status == 'i':
                    error_list = doc_status_info.get('errorList', [])
                    errors = [f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list]
                    msg += _("<br/><b>Erros reportados:</b><br/>%s", "<br/>".join(errors))

                move.message_post(body=msg)

            except UserError as e:
                move.write({'fe_status': 'not_sent'})
                move.message_post(body=_("<b>Falha ao enviar para AGT:</b> %s", e.args[0]))
                # Don't re-raise UserError to avoid generic RPC error dialog
            except Exception as e:
                _logger.exception("Erro inesperado ao enviar fatura para AGT.")
                move.write({'fe_status': 'not_sent'})
                move.message_post(body=_("<b>Ocorreu um erro inesperado:</b> %s", e))
                # Re-raise to show traceback in logs for debugging
                raise

    def action_check_fe_status(self):
        """Consulta o estado da fatura na AGT usando o submissionUUID."""
        self.ensure_one()
        if not self.fe_request_id:
            raise UserError(_("Não há um 'FE Request ID' para consultar o estado desta fatura."))

        service = self.env['l10n_ao.fe.service'].with_context(force_company=self.company_id.id)

        try:
            # 1. Consultar o estado na AGT
            response = service._get_agt_status(self.fe_request_id)

            # 2. Processar a resposta
            # Assuming the response structure from AGT's ObterEstado endpoint
            # This part might need adjustment based on actual AGT API documentation
            status_info = response.get('statusInfo', {})
            agt_status_code = status_info.get('statusCode')
            agt_status_message = status_info.get('statusMessage')

            new_fe_status = self.fe_status # Default to current status
            if agt_status_code == 'V': # Valid
                new_fe_status = 'v'
            elif agt_status_code == 'I': # Invalid
                new_fe_status = 'i'
            elif agt_status_code == 'P': # Pending (or similar)
                new_fe_status = 'processing'
            # Add other status mappings as needed

            self.write({
                'fe_status': new_fe_status,
                # Optionally store the full response for debugging/auditing
                # 'l10n_ao_fe_response_json': json.dumps(response, indent=2, ensure_ascii=False),
            })

            msg = _("Estado da fatura atualizado pela AGT:<br/>- Código: %s<br/>- Mensagem: %s", agt_status_code, agt_status_message)
            self.message_post(body=msg)

        except UserError as e:
            self.message_post(body=_("<b>Falha ao consultar estado na AGT:</b> %s", e.args[0]))
        except Exception as e:
            _logger.exception("Erro inesperado ao consultar estado da fatura na AGT.")
            self.message_post(body=_("<b>Ocorreu um erro inesperado ao consultar estado:</b> %s", e))
            raise

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
            qr_img = qr_img.resize((350, 350), Image.Resampling.LANCZOS)

            # Converter imagem para base64 e guardar na fatura
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            inv.fe_qr_code = base64.b64encode(buf.getvalue())
            buf.close()
