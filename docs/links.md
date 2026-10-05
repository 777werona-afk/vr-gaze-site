# 9. Ссылки и лицензии

## 9.1. Репозиторий и опубликованные сайты

| Что | Адрес |
|---|---|
| Репозиторий | <https://github.com/777werona-afk/vr-gaze-site> |
| Сайт на GitHub Pages | <https://777werona-afk.github.io/vr-gaze-site/> |
| Сайт на Cloudflare Pages | <https://vr-gaze-site.pages.dev> |
| Репозиторий GitHub Action | <https://github.com/777werona-afk/rsync-ssh-deploy> |
| Релиз `v1.0.0` и теги | <https://github.com/777werona-afk/rsync-ssh-deploy/releases/tag/v1.0.0> |
| Workflow, использующий action | [`deploy.yml`](https://github.com/777werona-afk/vr-gaze-site/blob/main/.github/workflows/deploy.yml), задание `deploy-ssh` |
| Страница в GitHub Marketplace | не опубликовано (см. [раздел 5.6](practice/action.md)) |
| Отечественный хостинг | не развёрнут (см. [заключение](conclusion.md)) |

## 9.2. Лицензии

Контент (`docs/`) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode.ru), код (`scripts/`, `Makefile`, `mkdocs.yml`, `.github/`) — MIT. Лицензии лежат в корне репозитория: `LICENSE-CONTENT.md` и `LICENSE`.

Сырые записи взгляда участников исследования ни одной из этих лицензий не покрываются: это персональные данные, их публикация требует отдельного согласия.

## 9.3. Дополнительные материалы

- [Исходные материалы курса на Яндекс.Диске](https://disk.yandex.ru/i/RRaTxrn5psk7ZQ)
- [MkDocs](https://www.mkdocs.org/) и [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Docs: создание composite action](https://docs.github.com/en/actions/sharing-automations/creating-actions/creating-a-composite-action)
- [GitHub Docs: публикация action в Marketplace](https://docs.github.com/en/actions/sharing-automations/creating-actions/publishing-actions-in-github-marketplace)
- [GitHub Docs: метаданные action (`action.yml`)](https://docs.github.com/en/actions/sharing-automations/creating-actions/metadata-syntax-for-github-actions)
- [Cloudflare Pages: Wrangler, `pages deploy`](https://developers.cloudflare.com/pages/get-started/direct-upload/)
- [Semantic Versioning 2.0.0](https://semver.org/lang/ru/)
