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
from odoo.tools.misc import file_path
import warnings
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
        compute='_compute_l10n_ao_fe_serie_id',
        store=True, readonly=False, precompute=True,
        copy=False
    )
    l10n_ao_fe_document_class_id = fields.Many2one(
        'l10n_ao.fe.document.class', 
        string="Tipo de Documento FE",
        compute='_compute_l10n_ao_fe_document_class_id',
        store=True, readonly=False, precompute=True
    )

    @api.depends('l10n_ao_fe_serie_id')
    def _compute_l10n_ao_fe_document_class_id(self):
        for move in self:
            move.l10n_ao_fe_document_class_id = move.l10n_ao_fe_serie_id.document_class_id

    l10n_ao_fe_queue_ids = fields.One2many('l10n_ao.fe.queue', 'invoice_id', string='Fila de Envio AGT')
    
    # Campo técnico para identificação de facturas vindas do POS
    is_pos_invoice = fields.Boolean(string="É Factura POS", default=False, copy=False)

    @api.depends('journal_id', 'move_type')
    def _compute_l10n_ao_fe_serie_id(self):
        for move in self:
            if not move.l10n_ao_fe_serie_id:
                if move.move_type == 'out_refund':
                    # Tenta a série de reembolso do diário, senão busca geral
                    if move.journal_id and move.journal_id.l10n_ao_fe_refund_serie_id:
                        move.l10n_ao_fe_serie_id = move.journal_id.l10n_ao_fe_refund_serie_id
                    else:
                        serie_nc = self.env['l10n_ao.fe.serie'].search([
                            ('document_class_id.code', '=', 'NC'),
                            ('agt_status', '=', 'active')
                        ], limit=1)
                        move.l10n_ao_fe_serie_id = serie_nc.id if serie_nc else False
                
                elif move.move_type == 'out_invoice':
                    # Verificar se é Nota de Débito (ND) - Geralmente tem debit_origin_id ou vem de diário ND
                    is_debit_note = hasattr(move, 'debit_origin_id') and move.debit_origin_id
                    
                    if is_debit_note:
                        if move.journal_id and move.journal_id.l10n_ao_fe_debit_serie_id:
                            move.l10n_ao_fe_serie_id = move.journal_id.l10n_ao_fe_debit_serie_id
                        else:
                            serie_nd = self.env['l10n_ao.fe.serie'].search([
                                ('document_class_id.code', '=', 'ND'),
                                ('agt_status', '=', 'active')
                            ], limit=1)
                            move.l10n_ao_fe_serie_id = serie_nd.id if serie_nd else move.journal_id.l10n_ao_fe_serie_id
                    elif move.journal_id and move.journal_id.l10n_ao_fe_serie_id:
                        move.l10n_ao_fe_serie_id = move.journal_id.l10n_ao_fe_serie_id
                else:
                    move.l10n_ao_fe_serie_id = False

    @api.onchange('journal_id', 'move_type')
    def _onchange_journal_id(self):
        if self.move_type == 'out_refund':
            if self.journal_id and self.journal_id.l10n_ao_fe_refund_serie_id:
                self.l10n_ao_fe_serie_id = self.journal_id.l10n_ao_fe_refund_serie_id
            else:
                serie_nc = self.env['l10n_ao.fe.serie'].search([
                    ('document_class_id.code', '=', 'NC'),
                    ('agt_status', '=', 'active')
                ], limit=1)
                if serie_nc:
                    self.l10n_ao_fe_serie_id = serie_nc
        
        elif self.move_type == 'out_invoice':
            is_debit_note = hasattr(self, 'debit_origin_id') and self.debit_origin_id
            if is_debit_note:
                if self.journal_id and self.journal_id.l10n_ao_fe_debit_serie_id:
                    self.l10n_ao_fe_serie_id = self.journal_id.l10n_ao_fe_debit_serie_id
                else:
                    serie_nd = self.env['l10n_ao.fe.serie'].search([
                        ('document_class_id.code', '=', 'ND'),
                        ('agt_status', '=', 'active')
                    ], limit=1)
                    if serie_nd:
                        self.l10n_ao_fe_serie_id = serie_nd
            elif self.journal_id and self.journal_id.l10n_ao_fe_serie_id:
                self.l10n_ao_fe_serie_id = self.journal_id.l10n_ao_fe_serie_id

    def action_post(self):
        # Primeiro, executa a confirmação padrão do Odoo (e de outros módulos)
        res = super(AccountMoveInherit, self).action_post()
        
        # Depois de confirmada, tenta enviar para a AGT automaticamente
        for move in self:
            _logger.info("FE AGT: Analisando envio automático para %s (Tipo: %s, Série: %s)", 
                         move.name, move.move_type, move.l10n_ao_fe_serie_id.name if move.l10n_ao_fe_serie_id else 'N/A')
            
            # Garantir que out_invoice (Fatura) e out_refund (Nota de Crédito) são enviadas
            if move.move_type in ('out_invoice', 'out_refund') and move.l10n_ao_fe_serie_id:
                try:
                    move.action_send_fe_agt()
                except Exception as e:
                    _logger.error("FE AGT: Erro no envio automático para %s: %s", move.name, str(e))
                    move.message_post(body=_("Erro no envio automático para a AGT: %s") % str(e))
            else:
                _logger.info("FE AGT: Salto de envio automático para %s (Condições não reunidas)", move.name)
        
        return res

    def _get_document_number_for_fe(self):
        """Constructs the document number based on the selected series or falls back to the invoice name.
        Ensures format: DocumentType + space + DocumentNo (e.g., FR FR6026S5139N/001)
        """
        self.ensure_one()
        doc_type = self.l10n_ao_fe_serie_id.document_class_id.code if self.l10n_ao_fe_serie_id else 'FT'
        document_no = self.name or ''
        
        # Se o nome já começa com o tipo do documento e um espaço, não repetimos
        if document_no.startswith(f"{doc_type} "):
            return document_no
        
        # Caso contrário, prefixamos conforme exigência da AGT para consulta
        return f"{doc_type} {document_no}"

    def action_send_fe_agt(self):
        """Gera o payload, envia para AGT e processa a resposta."""
        for move in self:
            service = self.env['l10n_ao.fe.service'].with_company(move.company_id)
            
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
                final_status = 'sent'
                if doc_status == 'V':
                    final_status = 'validated'
                    move.generate_qr_code()
                
                # Filtrar erros reais (ignorar strings vazias como [""])
                real_errors = [e for e in error_list if isinstance(e, dict) and (e.get('idError') or e.get('errorCode'))]
                
                if doc_status == 'I' or real_errors:
                    final_status = 'error'
                    error_msgs = "\n".join([f"({e.get('idError', e.get('errorCode'))}) {e.get('descriptionError', e.get('errorDescription'))}" for e in real_errors])
                    move.fe_error_list = error_msgs or str(error_list)
                
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

    def action_sync_status_from_query(self):
        """Tenta recuperar o estado da factura através do serviço de consulta (invoiceNo).
        Útil para quando a factura já existe na AGT mas o Odoo ficou com erro.
        """
        self.ensure_one()
        service = self.env['l10n_ao.fe.service'].with_context(force_company=self.company_id.id)
        document_no = self._get_document_number_for_fe()
        
        try:
            response = service.consultar_factura(document_no, self.company_id.vat)
            # Na resposta de consulta bem sucedida, o documentStatus vem dentro de 'document'
            # ou no root dependendo da versão. Vimos que vem no root como 'N' ou 'V'
            status = response.get('documentStatus')
            
            if status in ('N', 'V', 'P'):
                doc_data = response.get('document', {})
                vals = {
                    'fe_status': 'validated',
                    'fe_document_hash': doc_data.get('jwsSignature', '')[-4:],
                    'fe_last_response': json.dumps(response, indent=2, ensure_ascii=False)
                }
                self.write(vals)
                self.generate_qr_code()
                self.message_post(body=_("Fatura sincronizada com sucesso via Consulta AGT. Estado: %s") % status)
                return True
            else:
                error_list = response.get('errorList', [])
                raise UserError(_("AGT indica que o documento ainda não é válido ou não foi encontrado. Resposta: %s") % error_list)
        except Exception as e:
            raise UserError(_("Erro ao tentar sincronizar com AGT: %s") % str(e))

    def action_force_manual_validate(self):
        """Força a validação manual do documento. Apenas para administradores."""
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_("Apenas administradores de faturação podem forçar a validação manual."))
            
        for move in self:
            move.write({
                'fe_status': 'validated',
            })
            move.generate_qr_code()
            move.message_post(body=_("ATENÇÃO: Factura validada MANUALMENTE por um administrador. Certifique-se que o documento existe no portal da AGT."))
        return True

    def open_consultar_factura_wizard(self):
        self.ensure_one()
        # Garantir formato oficial para a consulta
        document_no = self._get_document_number_for_fe()
        return {
            'name': _('Consultar Fatura AGT'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.consult.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_no': document_no,
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
        """Gera QR Code conforme especificações actualizadas da AGT (Novo URL 2026)"""
        # Novo URL Oficial (AGT): https://quiosqueagt.hml.minfin.gov.ao/facturacao-eletronica/consultar-fe
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_ao_fe.qrcode_base_url', 
            "https://quiosqueagt.hml.minfin.gov.ao/facturacao-eletronica/consultar-fe"
        )

        for inv in self:
            if not inv.name:
                continue

            # NIF do Emissor (Remover prefixo de país se existir para o QR Code)
            nif_emissor = inv.company_id.vat or ""
            if nif_emissor.startswith('AO'):
                nif_emissor = nif_emissor[2:]
            
            # Número do documento completo (Tipo + Espaço + Numero)
            # Cada espaço deve ser substituído pela sequência %20
            full_document_no = inv._get_document_number_for_fe()
            document_no_encoded = full_document_no.replace(" ", "%20")
            
            # Montar URL final conforme especificação
            qr_url = f"{base_url}?emissor={nif_emissor}&document={document_no_encoded}"

            qr = qrcode.QRCode(
                version=4, # Versão 4 (33 x 33 módulos) conforme spec
                error_correction=ERROR_CORRECT_M, # Nível M (15%) conforme spec
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            # Adicionar logotipo da AGT ao centro
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
                _logger.warning("Não foi possível adicionar o logotipo ao QR Code: %s", e)

            # Redimensionar para 350x350 px (Requisito Fiscal)
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

    def action_regenerate_fe_qr_codes(self):
        """Actualiza os QR Codes de faturas já validadas com o novo formato e URL."""
        # Apenas para faturas que já têm QR Code gerado anteriormente
        moves = self.search([('fe_qr_code', '!=', False)])
        if moves:
            moves.generate_qr_code()
            return True
        return False
