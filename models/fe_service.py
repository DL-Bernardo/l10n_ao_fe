from odoo import models, _
from odoo.exceptions import UserError


class FEDeviceService(models.AbstractModel):
    _name = 'l10n_ao.fe.service'
    _description = 'Serviço de integração com AGT FE'

    def _get_conf(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'username': ICP.get_param('l10n_ao_fe.username'),
            'password': ICP.get_param('l10n_ao_fe.password'),
            'base_url': ICP.get_param('l10n_ao_fe.base_url', 'https://sifphml.minfin.gov.ao/sigt/fe/v1'),
            'private_key': ICP.get_param('l10n_ao_fe.private_key'),
            'product_id': ICP.get_param('l10n_ao_fe.product_id', 'ODFE_MOD_01'),
            'product_version': ICP.get_param('l10n_ao_fe.product_version', '1.0'),
            'software_validation_number': ICP.get_param('l10n_ao_fe.software_validation_number'),
        }

    def _handle_error_response(self, code, resp):
        """Centralized error handler"""
        error_list = resp.get('errorList', [])
        if error_list:
            error_messages = []
            for error in error_list:
                error_code = error.get('idError')
                error_description = error.get('descriptionError')
                
                # Try to find a more user-friendly message
                friendly_error = self.env['l10n_ao.fe.error.code'].search([('code', '=', error_code)], limit=1)
                if friendly_error:
                    message = f"({error_code}) {friendly_error.description}"
                else:
                    message = f"({error_code}) {error_description}"
                error_messages.append(message)
            
            final_message = "\n".join(error_messages)
            raise UserError(_("A AGT retornou os seguintes erros:\n\n%s", final_message))
        
        # Fallback for other errors
        error_detail = resp.get('error', str(resp))
        raise UserError(_("Erro de comunicação com a AGT (HTTP %s):\n%s", code, error_detail))

    def sign_object_rs256(self, obj: dict) -> str:
        conf = self._get_conf()
        private_key = conf.get('private_key')
        if not private_key:
            raise UserError(_('A chave privada (l10n_ao_fe.private_key) não está configurada!'))
        
        # Ensure keys are sorted for consistent signature generation
        payload = json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return jws.sign(payload.encode('utf-8'), private_key, algorithm='RS256')

    def build_software_info(self):
        conf = self._get_conf()
        return {
            'productId': conf.get('product_id'),
            'productVersion': conf.get('product_version'),
            'softwareValidationNumber': conf.get('software_validation_number'),
        }

    def _make_request(self, endpoint, payload):
        conf = self._get_conf()
        url = conf['base_url'].rstrip('/') + '/' + endpoint

        try:
            resp = requests.post(
                url, json=payload,
                auth=(conf['username'], conf['password']),
                headers={'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8'},
                timeout=60
            )
            resp.raise_for_status()
            return resp.status_code, resp.json()
        except requests.exceptions.JSONDecodeError:
            return resp.status_code, {'error': resp.text}
        except requests.exceptions.HTTPError as e:
            _logger.error("Erro HTTP ao comunicar com FE: %s, Resposta: %s", e, e.response.text)
            try:
                return e.response.status_code, e.response.json()
            except json.JSONDecodeError:
                return e.response.status_code, {'error': e.response.text}
        except Exception as e:
            _logger.exception("Erro ao comunicar com FE: %s", e)
            return 500, {'error': str(e)}

    def build_document_signature_fields(self, inv):
        return {
            'documentNo': inv.name,
            'taxRegistrationNumber': inv.company_id.vat or '',
            'documentType': inv.l10n_ao_fe_document_class_id.code,
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
        return self._make_request('registarFactura', payload)

    def obter_estado(self, request_id, company):
        software_info_detail = self.build_software_info()
        software_info = {
            'softwareInfoDetail': software_info_detail,
            'jwsSoftwareSignature': self.sign_object_rs256(software_info_detail)
        }

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
        return self._make_request('obterEstado', payload)

    def solicitar_serie(self, serie_code, doc_class_code, start_number, end_number, start_date, end_date=None):
        company = self.env.company
        software_info_detail = self.build_software_info()
        software_info = {
            'softwareInfoDetail': software_info_detail,
            'jwsSoftwareSignature': self.sign_object_rs256(software_info_detail)
        }

        serie_details = {
            'serieCode': serie_code,
            'documentClass': doc_class_code,
            'startNumber': str(start_number),
            'endNumber': str(end_number),
            'startDate': start_date.isoformat(),
        }
        if end_date:
            serie_details['endDate'] = end_date.isoformat()

        signature_payload = {
            'taxRegistrationNumber': company.vat or '',
            'serieCode': serie_code,
            'documentClass': doc_class_code,
        }
        jws_signature = self.sign_object_rs256(signature_payload)

        payload = {
            "schemaVersion": "1.0",
            "submissionGUID": str(uuid.uuid4()),
            "taxRegistrationNumber": company.vat or '',
            "submissionTimeStamp": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "softwareInfo": software_info,
            "serieDetails": serie_details,
            "jwsSignature": jws_signature,
        }
        return self._make_request('solicitarSerie', payload)

    def listar_series(self):
        company = self.env.company
        software_info_detail = self.build_software_info()
        software_info = {
            'softwareInfoDetail': software_info_detail,
            'jwsSoftwareSignature': self.sign_object_rs256(software_info_detail)
        }

        query_end_date = datetime.utcnow().date()
        query_start_date = query_end_date.replace(year=query_end_date.year - 1)

        signature_payload = {
            'taxRegistrationNumber': company.vat or '',
            'queryStartDate': query_start_date.isoformat(),
            'queryEndDate': query_end_date.isoformat(),
        }
        jws_signature = self.sign_object_rs256(signature_payload)

        payload = {
            "schemaVersion": "1.0",
            "submissionGUID": str(uuid.uuid4()),
            "taxRegistrationNumber": company.vat or '',
            "submissionTimeStamp": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "softwareInfo": software_info,
            "queryStartDate": signature_payload['queryStartDate'],
            "queryEndDate": signature_payload['queryEndDate'],
            "jwsSignature": jws_signature,
        }
        return self._make_request('listarSeries', payload)