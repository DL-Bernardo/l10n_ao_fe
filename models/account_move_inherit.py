# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.modules.module import get_module_resource
from datetime import datetime
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from io import BytesIO
import base64
from PIL import Image
import os


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    fe_request_id = fields.Char(string='FE Request ID')
    fe_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('processing', 'Processing'),
        ('v', 'Valid'),
        ('i', 'Invalid')
    ], string="Estado FE", default='not_sent')
    fe_qr_code = fields.Binary(string="QR Code AGT")

    # =====================================================
    # MÉTODO DE ENVIO PARA A AGT
    # =====================================================
    def action_send_fe(self):
        service = self.env['l10n_ao.fe.service']
        for inv in self:
            # 1. Construir as linhas da fatura
            lines = []
            for line in inv.invoice_line_ids.filtered(lambda l: not l.display_type):
                taxes = []
                for tax in line.tax_ids:
                    taxes.append({
                        'taxType': 'IVA',
                        'taxCountryRegion': 'AO',
                        'taxCode': 'NOR',
                        'taxPercentage': str(tax.amount),
                        'taxBase': str(line.price_subtotal),
                        'taxAmount': str(line.price_total - line.price_subtotal),
                    })

                lines.append({
                    'lineNumber': str(line.sequence),
                    'productCode': line.product_id.default_code or '',
                    'productDescription': line.name,
                    'quantity': str(line.quantity),
                    'unitOfMeasure': line.product_uom_id.name or '',
                    'unitPrice': str(line.price_unit),
                    'debitAmount': str(line.price_subtotal),
                    'taxes': taxes,
                })

            # 2. Construir os totais do documento
            document_totals = {
                'taxPayable': str(inv.amount_tax),
                'netTotal': str(inv.amount_untaxed),
                'grossTotal': str(inv.amount_total),
            }

            # 3. Construir o payload completo do documento
            document = {
                'documentNo': inv.name,
                'documentStatus': 'N',
                'documentDate': inv.invoice_date.isoformat() if inv.invoice_date else '',
                'documentType': 'FT' if inv.move_type == 'out_invoice' else 'NC',
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
            inv.write({
                'fe_status': 'processing'
            })
            inv.message_post(body="Fatura enviada para a fila de processamento da AGT.")

    # =====================================================
    # MÉTODO PARA GERAR O QR CODE (PADRÃO AGT)
    # =====================================================
    def generate_qr_code(self):
        """Gera QR Code conforme especificações da AGT"""
        base_url = "https://portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo="

        for inv in self:
            if not inv.name:
                continue

            document_no = inv.name.replace(" ", "%20")
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
                logo = Image.open(logo_path)
                qr_width, qr_height = qr_img.size

                # Redimensionar logo (20% do QR)
                logo_size = int(qr_width * 0.20)
                logo.thumbnail((logo_size, logo_size))
                pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                qr_img.paste(logo, pos)

            # Redimensionar para 350x350 px
            qr_img = qr_img.resize((350, 350), Image.LANCZOS)

            # Converter imagem para base64 e guardar na fatura
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            inv.fe_qr_code = base64.b64encode(buf.getvalue())
            buf.close()