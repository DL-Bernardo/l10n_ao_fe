# 🇦🇴 Odoo 17 – Integração de Facturação Electrónica (AGT)

### Módulo: `l10n_ao_fe`
**Autor:** Digitalub / ContasMais  
**Versão:** 1.0.0  
**Compatibilidade:** Odoo 17  
**Licença:** AGPL-3  

---

## 🧭 Descrição Geral

O módulo **l10n_ao_fe** implementa a integração direta entre o **Odoo 17** e o **sistema de Facturação Electrónica da AGT (Administração Geral Tributária)**, permitindo:

- Envio automático de facturas para validação via **webservice REST (registarFactura)**.  
- Geração de **assinaturas digitais JWS (RS256)** com **chave RSA de 2048 bits**.  
- Consulta e sincronização de estado de facturas enviadas.  
- Geração automática do **QR Code da AGT** nas facturas impressas (conforme DS-102 e normas técnicas da AGT).  
- Gestão de uma **fila de envio (queue)** para rastrear facturas pendentes, enviadas, ou com erro.

Este módulo foi desenhado para cumprir integralmente as normas da AGT para softwares certificados e interoperar com os seguintes serviços oficiais:

| Serviço REST | Descrição |
|---------------|------------|
| `registarFactura` | Registo e envio de facturas electrónicas |
| `obterEstado` | Consulta do estado de validação de uma factura |
| `listarFacturas` | Lista de facturas electrónicas emitidas |
| `consultarFactura` | Consulta detalhada de uma factura |
| `solicitarSerie` | Criação de séries de numeração de facturação |
| `listarSeries` | Listagem das séries registadas |
| `validarDocumento` | Confirmação ou rejeição de documentos |

---

## ⚙️ Funcionalidades Principais

- 🔐 **Assinatura Digital (JWS)**  
  Cada factura é assinada com **chave privada RSA** (2048 bits), gerando o campo `jwsSignature` com base nos elementos:

- 🧾 **Envio Automático de Facturas**  
O botão “**Enviar AGT**” aparece na ficha da factura (`account.move`), permitindo transmitir directamente o documento para o servidor da AGT.

- 🕒 **Fila de Envio (Queue)**  
As facturas são registadas em `l10n_ao.fe.queue`, controlando:
- Estado do envio (`draft`, `sent`, `processing`, `done`, `error`)
- Tentativas
- Última resposta da AGT
- Request ID da submissão

- 🧩 **QR Code AGT Integrado**  
Cada factura aprovada gera automaticamente o **QR Code oficial da AGT**, com os parâmetros técnicos definidos:
| Parâmetro | Valor |
|------------|--------|
| **Padrão** | QR Code Model 2 |
| **Versão** | 4 (33×33 módulos) |
| **Correção de erros** | M (15%) |
| **Codificação** | UTF-8 |
| **URL base** | `https://portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo=` |
| **Tamanho** | 350×350 px |
| **Logo AGT** | Opcional, ≤ 20% da área total |

---

## 🧩 Estrutura do Módulo
l10n_ao_fe/
├── init.py
├── manifest.py
├── README.md
├── models/
│ ├── init.py
│ ├── fe_service.py # Comunicação com Webservices da AGT
│ ├── fe_queue.py # Fila de envio de facturas
│ └── account_move_inherit.py # Extensão de account.move + QR Code
├── views/
│ ├── account_move_views.xml # Botão "Enviar AGT"
│ └── fe_queue_views.xml # Listagem da fila FE
├── data/
│ └── ir_config_parameter.xml # Parâmetros padrão
├── security/
│ └── ir.model.access.csv # Regras de acesso
└── static/
└── description/
├── icon.png # Ícone do módulo
└── agt_logo.png # Logo usado no QR Code

---

## 🛠️ Instalação

1. Copie o módulo para o diretório de addons do Odoo:
   ```bash
   /opt/odoo/addons/l10n_ao_fe
   
cd /etc/odoo/
openssl genrsa -out ChavePrivada.pem 2048
openssl rsa -in ChavePrivada.pem -outform PEM -pubout -out ChavePublica.pem

Depois, registe a Chave Pública no Portal do Parceiro da AGT
👉 https://parceiro.minfin.gov.ao

⚡ Fluxo Operacional

1. Emitir e validar uma fatura (account.move).
2. Clicar em “Enviar AGT”.

3. O módulo:
	* Monta o payload JSON;
	* Assina digitalmente (RS256);
	* Envia via API registarFactura;
	* Regista o resultado na fila (l10n_ao.fe.queue).
	* Após resposta da AGT, o QR Code é gerado e armazenado.
	* R é automaticamente impresso no relatório PDF da fatura.
    
    
| Método | Endpoint            | Descrição                      |
| ------ | ------------------- | ------------------------------ |
| `POST` | `/registarFactura`  | Regista facturas electrónicas  |
| `POST` | `/obterEstado`      | Consulta estado da factura     |
| `POST` | `/consultarFactura` | Consulta detalhe da factura    |
| `POST` | `/listarFacturas`   | Lista facturas do contribuinte |
| `POST` | `/solicitarSerie`   | Cria série de numeração        |
| `POST` | `/listarSeries`     | Lista séries existentes        |

OBS: Os Endpoint para /solicitarSerie e /listarSeries respectivamente Cria série de numeração e Lista séries existentes ainda não estão disponives ou seja a AGT ainda não enviou.

🧠 Segurança e Assinatura Digital

A assinatura JWS (JSON Web Signature) é gerada com a biblioteca python-jose, usando o algoritmo RS256, garantindo:

*Integridade dos dados enviados à AGT.
*Autenticidade da origem (software registado).
*Validação conforme o processo de certificação de software.

📦 Futuras Melhorias

*Integração automática de resposta obterEstado.
*Suporte completo para solicitarSerie e validarDocumento.
*Painel de logs de comunicação com a AGT.

📧 Suporte Técnico

Digitalub Angola – Prestação de Serviços e Comércio Geral, Lda
📩 suporte@digitalub.ao

🌐 https://digitalub.ao

📞 +244 976 269 330

Este módulo foi desenvolvido em conformidade com as especificações técnicas oficiais da AGT (DS-120 e DS-102) para softwares certificados de Facturação Electrónica.
