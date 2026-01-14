# Manual de Configuração - Facturação Electrónica AGT (Angola)
## Odoo 17 | Especificação 1.2

Este manual descreve os passos necessários para configurar e operar o módulo de Facturação Electrónica para Angola.

---

### 1. Requisitos Técnicos
Antes de instalar o módulo, certifique-se de que o servidor Odoo tem as seguintes bibliotecas Python instaladas:
* `pip install pycryptodome` (ou `cryptography` para JWS)
* `pip install qrcode[pil]`
* `pip install Pillow`
* `pip install requests`

---

### 2. Configurações da Empresa
Vá a **Definições > Empresas** e verifique:
1. **NIF:** Deve estar preenchido corretamente (ex: 5417247266).
2. **Morada:** Cidade, País (Angola) e Código de País (AO) devem estar configurados.

---

### 3. Parâmetros do Sistema (Integração AGT)
Vá a **Configuração > Técnico > Parâmetros do Sistema** para configurar os dados de acesso à AGT:
* `l10n_ao_fe.username`: Utilizador fornecido pela AGT.
* `l10n_ao_fe.password`: Palavra-passe da API.
* `l10n_ao_fe.software_id`: ID do Software fornecido pela AGT (ex: FE/85/AGT/2025).
* `l10n_ao_fe.private_key_issuer`: Chave privada PKCS#8 para assinatura JWS do Emissor.
* `l10n_ao_fe.public_key_issuer`: Chave pública correspondente (opcional, para verificação).
* `l10n_ao_fe.base_url`: URL base do serviço (Sem barra no final).
    * **Homologação:** `https://sifphml.minfin.gov.ao/sigt/fe/v1`
    * **Produção:** `https://sifp.minfin.gov.ao/sigt/fe/v1`

---

### 4. Configuração de Impostos
A AGT exige códigos de isenção específicos (M10, M02, etc.) para IVA 0%.
1. Vá a **Contabilidade > Configuração > Impostos**.
2. No separador **AGT (FE)**, defina o **Tipo de Imposto** (IVA ou IS).
3. Para impostos de taxa 0%, preencha obrigatoriamente o **Código de Isenção**.

---

### 5. Séries de Facturação
As faturas só podem ser enviadas se pertencerem a uma série autorizada pela AGT.
1. Vá a **Contabilidade > Configuração > Séries de Faturação**.
2. **Sincronizar:** Use o botão "Sincronizar Lista de Séries da AGT" para importar séries que já criou no portal da AGT.
3. **Solicitar:** Pode usar o Wizard "Solicitar Série" para criar uma nova série diretamente do Odoo.
4. **Diários:** No Diário de Vendas, associe a Série FE correspondente no campo dedicado.

---

### 6. Operação Diária
* **Faturas de Venda:** Ao confirmar uma fatura, o sistema tenta enviá-la automaticamente. Se falhar, fica com o estado "Erro" e poderá reenviar após corrigir os dados.
* **Recibos:** Pagamentos de faturas geram Recibos (RC). O sistema calcula as retenções na fonte (II ou IPU) proporcionalmente e envia o ficheiro eletrónico.
* **QR Code:** Após a validação, o QR Code aparece tanto no ecrã do Odoo como no PDF impresso.
* **Obter Estado:** Use este botão se o documento ficar preso em "Em Processamento" para consultar a resposta definitiva do servidor.

---

### 7. Resolução de Problemas Comuns
* **Erro E03:** Tipo de retenção inválido. (Resolvido: O módulo mapeia IPU/IAC para II).
* **Erro E21:** Inconsistência matemática. (Verificar se os preços unitários têm mais de 2 casas decimais ou arredondamentos incorretos).
* **Erro E08:** Documento já existe na AGT. (Geralmente ocorre em reenvios de documentos já aceites).

---
**Suporte Técnico:** Digitalub / ContasMais
**Certificação:** FE/85/AGT/2025
