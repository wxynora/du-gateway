# Cedareco upstream

- Source: `https://github.com/Zizuixixiang/cedareco`
- Pinned commit: `e600958941883a8be2cafe69f8b431bd64b71d03`
- License: PolyForm Noncommercial License 1.0.0
- Required notice: `Copyright (c) 2026 南山君 (https://github.com/Zizuixixiang/cedareco)`

The vendored runtime keeps the upstream engine, standalone HTTP service, static
pond UI, artwork, and standalone client. Upstream test/build helpers are not
part of the deployed runtime.

Downstream App mounting changes are limited to `web/index.html` and
`web/app.js`: the standalone connection form is fixed to the current protected
gateway mount instead of accepting another server URL. Pond simulation,
commands, state, codex, annals, and all six human disaster mini-games are
unchanged.
