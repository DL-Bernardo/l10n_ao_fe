import json
import uuid
import logging
from datetime import datetime, timezone

import requests
from jose import jws
from odoo import models

_logger = logging.getLogger(__name__)


class FEDeviceService(models.AbstractModel):
    _name = 'l10n_ao.fe.service'
    _description = 'Serviço de integração com AGT FE'

    def _get_conf(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'username': ICP.get_param('fe.username'),
            'password': ICP.get_param('fe.password'),
            'base_url': ICP.get_param('fe.base_url', 'https://sifphml.minfin.gov.ao/sigt/fe/v1'),
            'private_key': ICP.get_param('fe.private_key'),
            'product_id': ICP.get_param('fe.product_id'),
            'product_version': ICP.get_param('fe.product_version'),
            'software_validation_number': ICP.get_param('fe.software_validation_number'),
        }

    def sign_object_rs256(self, obj: dict) -> str:
        conf = self._get_conf()
        private_key = conf.get('private_key')
        if not private_key:
            raise ValueError('A chave privada (fe.private_key) não está configurada!')
        payload = json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
        return jws.sign(payload, private_key, algorithm='RS256')

    def build_software_info(self):
        conf = self._get_conf()
        return {
            'productId': conf.get('product_id'),
            'productVersion': conf.get('product_version'),
            'softwareValidationNumber': conf.get('software_validation_number'),
        }

    def build_document_signature_fields(self, inv):
        return {
            'documentNo': inv.name,
            'taxRegistrationNumber': inv.company_id.vat or '',
            'documentType': inv.move_type == 'out_invoice' and 'FT' or 'NC',
            'documentDate': inv.invoice_date.isoformat() if inv.invoice_date else '',
            'customerTaxID': inv.partner_id.vat or '',
            'customerCountry': inv.partner_id.country_id.code or 'AO',
            'companyName': inv.company_id.name,
            'documentTotals': {
                'grossTotal': inv.amount_total,
                'netTotal': inv.amount_untaxed,
                'taxPayable': inv.amount_tax,
            },
        }

    def registar_facturas(self, company, documents: list):
        conf = self._get_conf()
        url = conf['base_url'].rstrip('/') + '/registarFactura'

        software_info_detail = self.build_software_info()
        software_info = {
            'softwareInfoDetail': software_info_detail,
            'jwsSoftwareSignature': self.sign_object_rs256(software_info_detail)
        }

        payload = {
            'schemaVersion': '1.0',
            'submissionGUID': str(uuid.uuid4()),
            'taxRegistrationNumber': company.vat or '',
            'submissionTimeStamp': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            'softwareInfo': software_info,
            'numberOfEntries': str(len(documents)),
            'documents': documents,
        }

        try:
            resp = requests.post(
                url, json=payload,
                auth=(conf['username'], conf['password']),
                headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                timeout=60
            )
            return resp.status_code, resp.json()
        except requests.exceptions.JSONDecodeError:
            return resp.status_code, {'error': resp.text}
        except Exception as e:
            _logger.exception("Erro ao comunicar com FE: %s", e)
            return 500, {'error': str(e)}

    def obter_estado(self, request_id, company):
        conf = self._get_conf()
        url = conf['base_url'].rstrip('/') + '/obterEstado'

        software_info_detail = self.build_software_info()
        software_info = {
            'softwareInfoDetail': software_info_detail,
            'jwsSoftwareSignature': self.sign_object_rs256(software_info_detail)
        }

        # Assinatura específica para este pedido
        signature_payload = {
            'taxRegistrationNumber': company.vat or '',
            'requestID': request_id,
        }
        jws_signature = self.sign_object_rs256(signature_payload)

        payload = {
            "schemaVersion": "1.0",
            "submissionGUID": str(uuid.uuid4()),
            "taxRegistrationNumber": company.vat or '',
            "submissionTimeStamp": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "softwareInfo": software_info,
            "requestID": request_id,
            "jwsSignature": jws_signature
        }

        try:
            resp = requests.post(
                url, json=payload,
                auth=(conf['username'], conf['password']),
                headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                timeout=30
            )
            return resp.status_code, resp.json()
        except requests.exceptions.JSONDecodeError:
            return resp.status_code, {'error': resp.text}
        except Exception as e:
            _logger.exception("Erro ao obter estado: %s", e)
            return 500, {'error': str(e)}