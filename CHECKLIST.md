# Что сделать вручную

Всё, что можно было подготовить без доступа к вашим аккаунтам, уже в репозитории. Остальное — по шагам:

1. **Данные.** Скачайте `dataset.zip` с Google Drive, положите CSV в `data/raw/` (видео `.mp4` не коммитьте). По желанию создайте `data/DATASET_VERSION` с одной строкой, например `pilot-v1`. Запустите `make strict` и проверьте таблицу на странице P3: баннер «ДЕМО-ДАННЫЕ» должен исчезнуть.
2. **Репозиторий.** Создайте на GitHub пустой публичный репозиторий `vr-gaze-site` (если назовёте иначе — замените имя в `mkdocs.yml`, `README.md`, `docs/links.md` и `.github/workflows/deploy.yml`). Затем:
   ```bash
   git remote add origin https://github.com/777werona-afk/vr-gaze-site.git
   git add -A && git commit -m "Сайт с результатами: MkDocs, P3, T3"
   git branch -M main && git push -u origin main
   ```
3. **GitHub Pages.** Settings → Pages → Source = **GitHub Actions**.
4. **Хостинг (Helios или другой).** Создайте deploy-ключ (`ssh-keygen -t ed25519 -f deploy_key -N ""`), добавьте публичную часть на сервер, а в Settings → Secrets and variables → Actions заведите секреты `HOSTING_HOST`, `HOSTING_USER`, `HOSTING_PATH`, `HOSTING_SSH_KEY`, `HOSTING_KNOWN_HOSTS` (результат `ssh-keyscan -H <host>`, сверенный с отпечатком хоста) и переменную `HOSTING_SITE_URL` с адресом сайта на хостинге. Пока секретов нет, шаг выкладки пропускается.
5. **Первый запуск.** После push откройте вкладку Actions. Сделайте скриншоты зелёного запуска и намеренно проваленного (добавьте битую ссылку, см. раздел «Отладка»).
6. **Заполнить на сайте.** Найдите на страницах блоки «Заполнить после первого запуска» и замените их скриншотами и замерами из CI. Адрес сайта на хостинге внесите в `docs/links.md`.
7. **Ответ на задание.** Ссылку на сайт разместите как ответ.
