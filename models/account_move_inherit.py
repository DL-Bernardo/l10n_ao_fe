# -*- coding: utf-8 -*-
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


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    fe_request_id = fields.Char(string='FE Request ID', readonly=True, copy=False)
    fe_status = fields.Selection([
        ('not_sent', 'Não Enviada'),
        ('processing', 'Em Processamento'),
        ('v', 'Válida'),
        ('i', 'Inválida')
    ], string="Estado AGT", default='not_sent', readonly=True, copy=False)
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

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        # Logic to auto-select series based on journal can be added here
        pass

    def _get_document_number_for_fe(self):
        """Constructs the document number based on the selected series or falls back to the invoice name."""
        self.ensure_one()
        if not self.l10n_ao_fe_serie_id or not self.l10n_ao_fe_serie_id.sequence_id:
            # Fallback for testing without a series
            return self.name
        
        sequence = self.l10n_ao_fe_serie_id.sequence_id
        return f"{sequence.prefix}{self.name.split(' ')[-1]}"

    def action_post(self):
        """Assigns the sequence number upon validation."""
        # for move in self:
        #     if move.l10n_ao_fe_serie_id and move.state == 'draft':
        #         sequence = move.l10n_ao_fe_serie_id.sequence_id
        #         move.name = sequence.next_by_id()
        return super(AccountMoveInherit, self).action_post()

    def action_send_fe(self):
        service = self.env['l10n_ao.fe.service']
        for inv in self:
            # if not inv.l10n_ao_fe_serie_id:
            #     raise UserError(_("Por favor, selecione uma Série de Faturação Eletrónica para este documento."))

            # 1. Construir as linhas da fatura
            lines = []
            for line in inv.invoice_line_ids.filtered(lambda l: not l.display_type):
                taxes = []
                for tax in line.tax_ids:
                    tax_data = {
                        'taxType': 'IVA',
                        'taxCountryRegion': 'AO',
                        'taxCode': 'NOR', # This could be more dynamic
                        'taxPercentage': str(tax.amount),
                        'taxBase': str(line.price_subtotal),
                        'taxAmount': str(line.price_total - line.price_subtotal),
                    }
                    if tax.l10n_ao_fe_exemption_code:
                        tax_data['taxExemptionCode'] = tax.l10n_ao_fe_exemption_code
                    
                    taxes.append(tax_data)

                lines.append({
                    'lineNumber': str(line.sequence),
                    'productCode': line.product_id.default_code or '',
                    'productDescription': line.name,
                    'quantity': str(line.quantity),
                    'unitOfMeasure': line.product_uom_id.name or '',
                    'unitPrice': str(line.price_unit),
                    'debitAmount': str(line.price_subtotal) if inv.move_type in ('out_invoice', 'out_refund') else '0.0',
                    'creditAmount': str(line.price_subtotal) if inv.move_type == 'in_refund' else '0.0',
                    'taxes': taxes,
                })

            # 2. Construir os totais do documento
            document_totals = {
                'taxPayable': str(inv.amount_tax),
                'netTotal': str(inv.amount_untaxed),
                'grossTotal': str(inv.amount_total),
            }

            # 3. Construir o payload completo do documento
            document_no = inv._get_document_number_for_fe()
            document_type = inv.l10n_ao_fe_document_class_id.code if inv.l10n_ao_fe_document_class_id else 'FT'
            document = {
                'documentNo': document_no,
                'documentStatus': 'N',
                'documentDate': inv.invoice_date.isoformat() if inv.invoice_date else '',
                'documentType': document_type,
                'systemEntryDate': datetime.now().isoformat(),
                'customerTaxID': inv.partner_id.vat or '999999999',
                'customerCountry': inv.partner_id.country_id.code or 'AO',
                'companyName': inv.company_id.name,
                'lines': lines,
                'documentTotals': document_totals,
            }

            # 4. Assinar o documento
            signature_data = service.build_document_signature_fields(inv)
            document['jwsSignature'] = service.sign_object_rs256(signature_data)

            # 5. Criar o registo na fila
            self.env['l10n_ao.fe.queue'].create({
                'invoice_id': inv.id,
                'payload': document,
                'state': 'draft',
            })

            # 6. Atualizar o estado e notificar o utilizador
            inv.write({'fe_status': 'processing'})
            inv.message_post(body=_("Fatura enviada para a fila de processamento da AGT."))

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