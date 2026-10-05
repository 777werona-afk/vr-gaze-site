# Приложение А. Тексты пайплайнов

Листинги подключаются прямо из файлов репозитория при сборке сайта, поэтому не расходятся с реальными файлами. Комментарии написаны в самих файлах.

## А.1. Workflow сайта (`.github/workflows/deploy.yml`)

```yaml
--8<-- ".github/workflows/deploy.yml"
```

## А.2. Описание action (`action.yml`)

Файл из репозитория [rsync-ssh-deploy](https://github.com/777werona-afk/rsync-ssh-deploy), версия `v1.0.0`.

```yaml
--8<-- "listings/action.yml"
```

## А.3. Тестовый workflow action (`.github/workflows/test.yml`)

```yaml
--8<-- "listings/action-test.yml"
```

## А.4. Перестановка мажорного тега (`.github/workflows/release.yml`)

```yaml
--8<-- "listings/action-release.yml"
```
