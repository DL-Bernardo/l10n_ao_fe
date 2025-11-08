# -*- coding: utf-8 -*-
from odoo import models, fields, api
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
    ], default='not_sent')
    fe_qr_code = fields.Binary(string="QR Code AGT")  # <- campo binário pro QR

    # =====================================================
    # MÉTODO DE ENVIO PARA A AGT
    # =====================================================
    def action_send_fe(self):
        for inv in self:
            document = {
                'documentNo': inv.name,
                'documentType': 'FT',
                'documentDate': inv.invoice_date.isoformat() if inv.invoice_date else '',
                'customerTaxID': inv.partner_id.vat or '',
                'customerCountry': inv.partner_id.country_id.code or '',
                'companyName': inv.company_id.name,
                'documentTotals': inv.amount_total,
            }
            queue = self.env['l10n_ao.fe.queue'].create({
                'invoice_id': inv.id,
                'payload': document,
            })
            # assinatura exigida pela AGT
            signature_data = service.build_document_signature_fields(inv)
            document['jwsSignature'] = service.sign_object_rs256(signature_data)

            queue = self.env['l10n_ao.fe.queue'].create({
                'invoice_id': inv.id,
                'payload': document,
            })
            queue.action_send()
            inv.fe_status = 'processing'
            inv.fe_request_id = queue.request_id

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
            logo_path = "/opt/odoo17/odoo-server/addons_digitalub/l10n_ao_fe/static/description/agt_logo.png"
            if os.path.exists(logo_path):
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