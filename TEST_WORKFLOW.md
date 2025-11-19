# Workflow de Teste e Validação - Módulo l10n_ao_fe

Este documento guia-o através do processo de configuração e teste do módulo de Faturação Electrónica de Angola (AGT) no Odoo.

## 1. Pré-requisitos

Certifique-se de que as bibliotecas Python necessárias estão instaladas no ambiente onde o Odoo está a correr:

```bash
pip install requests python-jose[cryptography] qrcode Pillow
```

## 2. Configuração do Sistema

Antes de enviar faturas, é necessário configurar os parâmetros de autenticação e assinatura.

1.  **Ative o Modo de Programador** no Odoo (Settings -> Scroll down -> Activate the developer mode).
2.  Aceda a **Definições > Técnico > Parâmetros do Sistema**.
3.  Crie/Verifique as seguintes chaves:

| Chave | Valor (Exemplo) | Descrição |
| :--- | :--- | :--- |
| `l10n_ao_fe.base_url` | `https://sifphml.minfin.gov.ao/sigt/fe/v1` | URL da API (Homologação ou Produção) |
| `l10n_ao_fe.username` | `seu_usuario_agt` | Utilizador fornecido pela AGT |
| `l10n_ao_fe.password` | `sua_senha_agt` | Password fornecida pela AGT |
| `l10n_ao_fe.private_key_path` | `/caminho/para/chave_software.pem` | Chave Privada do SOFTWARE (Produtor) |
| `l10n_ao_fe.issuer_private_key_path` | `/caminho/para/chave_emissor.pem` | Chave Privada do EMISSOR (Cliente) |
| `l10n_ao_fe.product_id` | `DIGITALUB-FE` | ID do Produto Software Validado |
| `l10n_ao_fe.product_version` | `1.0.0` | Versão do Software Validado |
| `l10n_ao_fe.software_validation_number` | `0000/AGT/2025` | Número de Validação do Software |

**Nota:** O ficheiro `.pem` deve ser legível pelo utilizador que executa o serviço Odoo.

## 3. Cenário de Teste: Gestão de Séries e Envio

Este fluxo valida desde a solicitação da série até ao envio da fatura.

### 3.1. Solicitar Nova Série à AGT
1.  Vá a **Faturação > Configuração > Séries FE AGT**.
2.  Clique em **"Solicitar Série AGT"** (botão ou menu de ação, se disponível) ou crie um registo manualmente e procure o botão de solicitação.
    *   *Nota: Se o botão não estiver visível diretamente, verifique se existe um menu "Solicitar Série" em Configuração ou use o Wizard diretamente.*
    *   **Melhor Opção:** Vá a **Faturação > Configuração > Solicitar Série AGT** (se o menu foi criado) ou procure a ação no menu técnico.
3.  Preencha o Wizard:
    *   **Tipo de Documento:** Fatura (FT)
    *   **Número Inicial:** 1
    *   **Número Final:** 100 (ou conforme necessidade)
    *   **Data Início:** Hoje
4.  Clique em **"Solicitar"**.
5.  **Resultado Esperado:**
    *   Mensagem de sucesso: "Série solicitada e criada com sucesso!".
    *   Uma nova série é criada em `l10n_ao.fe.serie`.
    *   Uma nova sequência (`ir.sequence`) é criada no Odoo com o prefixo da série (ex: `FT2025.../`).

### 3.2. Criar e Enviar Fatura
1.  **Criar Fatura:**
    *   Vá a **Faturação > Clientes > Faturas**.
    *   Crie uma nova fatura.
    *   **Importante:** No campo "Diário" ou "Série", certifique-se que a fatura vai usar a sequência criada no passo anterior.
        *   *Dica:* Pode ser necessário associar a nova sequência ao Diário de Vendas ou selecionar a série manualmente no campo "Série de FE" (se editável).
    *   Confirme a fatura.
    *   Verifique se o número da fatura (`name`) segue o formato `<SeriesCode>/<Num>` (ex: `FT2025.../1`).
2.  **Enviar para a AGT:**
    *   No cabeçalho da fatura, clique no botão vermelho **"Enviar FE AGT"**.
    *   O sistema irá gerar o payload (agora incluindo o `seriesCode`), assinar e enviar.
    *   Observe o campo **"Estado FE"** (Badge) mudar de "Não Enviado" para "Em Processamento" ou "Enviado".
    *   Verifique o chatter (lado direito) para ver a mensagem de sucesso com o `Request ID`.

3.  **Verificar Payload e Logs:**
    *   Clique no botão **"Payload JSON"** para ver exatamente o que foi enviado.
    *   Vá ao menu **Faturação > Configuração > Logs FE AGT** para ver o registo técnico do pedido e da resposta.

4.  **Consultar Estado (Assíncrono):**
    *   Se a fatura ficar em "Em Processamento", clique no botão **"Obter Estado"**.
    *   Isto fará uma chamada ao endpoint `/obterEstado` usando o `Request ID` guardado.

5.  **Validar PDF:**
    *   Se o estado for "Enviado" ou "Validado", clique em **"Baixar Factura Electrónica"**.
    *   Abra o PDF gerado.
    *   Verifique se o **QR Code** está presente.
    *   Verifique se o **Hash** e a **Assinatura** aparecem abaixo do QR Code.

## 4. Resolução de Problemas Comuns

*   **Erro "O caminho para a chave privada não está configurado":**
    *   Verifique o parâmetro `l10n_ao_fe.private_key_path`.
*   **Erro de Assinatura (JWS):**
    *   Verifique se a chave privada corresponde à chave pública carregada no portal da AGT.
    *   Verifique se o algoritmo é `RS256`.
*   **Erro AGT (ex: NIF inválido):**
    *   O erro aparecerá no chatter e na lista de erros da fatura. Corrija os dados do cliente ou da empresa e tente enviar novamente (se a AGT permitir reenvio com mesmo número) ou cancele e crie uma nova.

## 5. Comandos Úteis (Shell Odoo)

Para testar a geração de assinatura manualmente na shell do Odoo:

```python
service = env['l10n_ao.fe.service']
# Testar leitura da chave
key = service._get_private_key()
print(len(key))

# Testar assinatura simples
sig = service._sign_payload({'teste': 123})
print(sig)
```
