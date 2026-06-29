RUFA GOLD ERP - نظام الحفظ الدائم

تم تعديل نظام الحفظ ليعمل بهذه الأولوية:

1) DATABASE_URL
   إذا أضفت DATABASE_URL في Render سيتم استخدام PostgreSQL تلقائياً، وهذا هو الأفضل للحفظ السحابي الدائم.

2) DATA_DIR أو /var/data
   إذا لم توجد DATABASE_URL سيحفظ النظام قاعدة SQLite والملفات داخل DATA_DIR أو /var/data.
   على Render يجب تفعيل Persistent Disk وربطه بالمسار /var/data حتى لا تختفي البيانات.

3) الصور والملفات
   لم تعد الصور تحفظ داخل static/uploads داخل المشروع.
   الصور تحفظ في مجلد دائم uploads داخل DATA_DIR أو /var/data وتظهر عبر رابط /uploads/filename.

المطلوب في Render للحفظ الممتاز:
- الأفضل: أضف PostgreSQL وانسخ DATABASE_URL في Environment Variables.
- للصور: فعّل Persistent Disk بمسار /var/data أو استخدم DATA_DIR=/var/data.

تنبيه:
إذا لم تضف PostgreSQL ولم تفعل Persistent Disk، أي منصة سحابية قد تمسح الملفات بعد إعادة النشر.
