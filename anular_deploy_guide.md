# Guia de Deploy Offline: Anulação de Faturas na AGT / Local

Este guia documenta as alterações realizadas de forma a garantir que a funcionalidade "Anular Factura" comunica corretamente com o serviço da AGT (`registarFactura` com status `A`) e lida com a certificação do Odoo sem bloqueios de "estado Rascunho".

Siga estes passos quando precisar de colocar estas alterações em servidores offline ou "air-gapped" (onde não pode usar simplesmente o comando `git pull`).

## 1. Ficheiros Novos Criados

Deverá copiar integralmente estes dois novos ficheiros para a máquina de destino:

* **Módulo:** `l10n_ao_fe`
* **Destino:** `l10n_ao_fe/wizard/fe_cancel_wizard.py`
    * *Contém a lógica do popup para escolher o Motivo de Anulação ('I' ou 'N') e invoca o serviço passando o `cancel_reason`.*
* **Destino:** `l10n_ao_fe/wizard/fe_cancel_wizard_views.xml`
    * *Contém a interface visual (popup) associada.*

## 2. Ficheiros Modificados

Substitua os ficheiros antigos no servidor offline pela versão atualizada (que já transporta na sua pen-drive ou máquina), ou aplique as seguintes edições diretas:

### No Módulo `l10n_ao_fe`

1. **`wizard/__init__.py`**
   * **Alteração:** Adicionada a linha `from . import fe_cancel_wizard` no final do ficheiro.
2. **`__manifest__.py`**
   * **Alteração:** Registado `'wizard/fe_cancel_wizard_views.xml',` dentro da secção `data`.
3. **`security/ir.model.access.csv`**
   * **Alteração:** Inseridas as permissões de utilizador base para acederem à nova janela da AGT. (`access_l10n_ao_fe_cancel_wizard...`)
4. **`models/fe_service.py`**
   * **Alteração:** A função `registar_factura` agora aceita um novo parâmetro `cancel_reason`. Quando este é fornecido, ele injeta `documentStatus: "A"` e `documentCancelReason` ao Payload.
5. **`models/account_move_inherit.py`**
   * **Alteração:** O botão de anular local anterior foi substituído por `action_open_cancel_fe_wizard()`, limitando e protegendo a anulação apenas para faturas que estejam em `fe_status == 'validated'`.
6. **`views/account_move_views.xml`**
   * **Alteração:** Substituído o botão "Anular" original pelo novo botão "Anular Factura (AGT)" com as condições restritivas de visibilidade (`fe_status != 'validated'`). Foi permitida a consulta do PDF para estados `cancelled`, e foi adicionado um `xpath` protetor que oculta a funcionalidade de Cancelamento interno se a factura AGT estiver com comunicação pendente ou confirmada.

### No Módulo de Certificação `opc_certification_ao_v17`

1. **`models/account_move.py`**
   * **Alteração:** Na função `write(self, vals)`, inseriu-se um bypass de segurança via contexto Odoo (`force_cancel_agt`) na etapa em que barra faturas assinadas de ir para o Estado **Rascunho** (Draft). Isto permite agora que a anulação interna corra até ao fim.
   * *Exemplo de Código Alvo:*
   ```python
   if previous_state != 'draft' and vals['state'] == 'draft' and self.move_type in ['out_invoice', 'out_refund']:
       if not self._context.get('force_cancel_agt'):
           raise ValidationError(_("Não pode alterar a fatura para rascunho."))
   ```

## 3. Comandos de Aplicação (Deploy Manual)

Após transferir e substituir estes ficheiros na pasta física correspondente de cada módulo em `/opt/odoo/` ou `/odoo/odoo-server/addons` no servidor de produção offline, aplique as atualizações na base de dados:

1. Pare o serviço caso exista encravamento de memória ou processos órfãos:
   ```bash
   sudo pkill -f odoo
   ```

2. Refresque rigorosamente a Base de Dados e os 2 módulos alterados. É mandatário listar a base de dados em utilização e atualizar:
   ```bash
   sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d NOME_DA_SUA_BD -u l10n_ao_fe,opc_certification_ao_v17 --stop-after-init
   ```

3. Volte a reiniciar os serviços de forma permanente em "background" (modo produção standard que a sua cloud / ambiente use):
   ```bash
   nohup sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf &
   ```

Após os serviços estarem novamente online, as alterações estarão disponíveis para uso final de Faturação/Contabilidade.
