"""Canonical catalog of platform capabilities (features) for the RBAC model.

Profiles (ds.perfis) store a jsonb array of these capability keys in `permissoes`;
the Configurações → Perfis UI renders this catalog as toggles. Keeping the catalog
in code (not the DB) means the app always knows its own feature set, and adding a
feature is a code change + a toggle — never a schema migration.

`data_scope` (loja|equipa|propria|nenhuma) is a separate per-profile field on
ds.perfis, resolved in core/scope.py — it governs CRM data visibility, not feature
access, so it is NOT part of this capability catalog.

Note: newsletter authoring is a PER-USER grant (platform_users.can_newsletter),
not a profile capability, because two users on the same profile (bs, jg) differ on
it. It deliberately does not appear here.
"""
from __future__ import annotations

# key -> (grupo, rótulo PT). Order within a group is display order.
CAPABILITIES: dict[str, tuple[str, str]] = {
    # ---- Páginas (nav) ----
    "page.contactos":     ("Páginas", "Contactos"),
    "page.dashboard":     ("Páginas", "Dashboard"),
    "page.leads":         ("Páginas", "Leads"),
    "page.newsletter":    ("Páginas", "Newsletter"),
    "page.recap":         ("Páginas", "Recap semanal"),
    "page.analise_documental": ("Páginas", "Análise documental"),
    "page.crm_live":      ("Páginas", "CRM em direto"),
    "page.configuracoes": ("Páginas", "Configurações"),
    # ---- Ações ----
    "users.manage":     ("Ações", "Gerir utilizadores"),
    "teams.manage":     ("Ações", "Gerir equipas"),
    "profiles.manage":  ("Ações", "Editar perfis e permissões"),
    "crm.sync":         ("Ações", "Sincronizar CRM"),
    "loja.edit":        ("Ações", "Editar dados da loja"),
    "messaging.send":   ("Ações", "Enviar mensagens a clientes"),
    "messaging.config": ("Ações", "Configurar canais e limites de envio"),
}

# Every real page path we gate, mapped to its capability key. Used by the frontend
# nav filter (via /me) and any server-side page guard we may add later.
PAGE_CAPABILITY: dict[str, str] = {
    "/contactos":      "page.contactos",
    "/dashboard":      "page.dashboard",
    "/leads":          "page.leads",
    "/newsletter":     "page.newsletter",
    "/recap":          "page.recap",
    "/analise-documental": "page.analise_documental",
    "/clientes-live":  "page.crm_live",
    "/configuracoes":  "page.configuracoes",
}

ALL_CAPABILITIES: frozenset[str] = frozenset(CAPABILITIES)


def catalog() -> list[dict]:
    """Catalog shaped for the UI: [{key, grupo, rotulo}] in declaration order."""
    return [
        {"key": k, "grupo": grupo, "rotulo": rotulo}
        for k, (grupo, rotulo) in CAPABILITIES.items()
    ]


def valid_caps(caps: list[str] | None) -> list[str]:
    """Keep only known capability keys, de-duplicated, in catalog order."""
    given = set(caps or [])
    return [k for k in CAPABILITIES if k in given]
