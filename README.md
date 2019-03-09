# stringslator

Simple system strings localization for the masses. NSLocalizedString()



## What is it?

This script was inspired by an App called [System Strings][1] by Oleg Andreev. The functionality is similar but doesn't rely on a dictionary that is distributed together with the application.

Instead this script will parse all translation files (`.strings`
files) that are already present in the operating system. Common translations like 'Abort' were already translated by Apple Inc. (and other software distributors).



## Usage

First we have to create an index on some files. Lets start with macOS' system applications.

```
stringslator.py add -r /System/
```

This takes roughly 1 minute. The SQLite database is now initialized (133mb with 1.7M strings) in the same directory as the python script. We can start searching for some translations:

```
stringslator.py search "Update s%"
```
```
  141 | Update Security Code  ---  ('UPDATECODE')
  320 | Update Services  ---  ('kPerformSDPQueryKey')
  454 | Update suchen  ---  ('SOFTWARE_UPDATE_FINDING')
  454 | Update suchen  ---  ('MIGRATION_UPDATE_FINDING')
 1747 | Update Services  ---  ('kPerformSDPQueryKey')

5 results.
```

Notice here, we used `%` to match an arbitrary suffix. Use `_` for a single character wildcard. SQLite like matching rules apply. (see Notes below for language specific search). This view can get quite loaded, you can pipe the result into `less -S`.

After we found a translation we want, lets export the translations for all available languages. For that, we use the first column id and the title-key value inside `('...')`.

```
stringslator.py export 141 "UPDATECODE"
```
```
ar|تحديث رمز الأمن
ca|Actualitzar codi de seguretat
cs|Aktualizovat zabezpečovací kód
da|Opdater sikkerhedskode
de|Sicherheitscode aktualisieren
el|Ενημέρωση κωδικού ασφαλείας
en|Update Security Code
es|Actualizar código de seguridad
es_419|Actualizar código de seguridad
fi|Päivitä suojakoodi
fr|Mettre à jour le code de sécurité
he|עדכן/י קוד אבטחה
hi|सुरक्षा कोड अपडेट करें
hr|Ažuriraj sigurnosni kôd
hu|Biztonsági kód frissítése
id|Perbarui Kode Keamanan
it|Aggiorna codice di sicurezza
ja|セキュリティコードをアップデート
ko|보안 코드 업데이트
ms|Kemas Kini Kod Keselamatan
nl|Werk beveiligingscode bij
no|Oppdater sikkerhetskode
pl|Uaktualnij kod bezpieczeństwa
pt|Atualizar Código de Segurança
pt_PT|Atualizar código de segurança
ro|Actualizează codul de securitate
ru|Обновить код безопасности
sk|Aktualizovať bezpečnostný kód
sv|Uppdatera säkerhetskod
th|อัพเดทรหัสความปลอดภัย
tr|Güvenlik Kodunu Güncelle
uk|Оновити захисний код
vi|Cập nhật Mã Bảo mật
zh_CN|更新安全码
zh_TW|更新安全碼
```

For a quick translation job this should be sufficient. If you need some advanced processing, you can also use the SQLite db directly.

If you later decide to add or remove additional applications to the db, use the `add` and `delete` commands respectively. Apps can also be deleted by their file-id. All commands show a help `-h` window to describe available options.



## Notes

Search will always search case independent and by default English and German translations. If you want to change this behavior go to `cli_search` and modify `langs=["en%", "de%", "Ger%"]`.


[1]: https://itunes.apple.com/us/app/system-strings/id570467776?l=en