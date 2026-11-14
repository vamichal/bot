from django.test import SimpleTestCase


class StaticFilesTest(SimpleTestCase):
    """whitenoise отдаёт статику из приложений, без collectstatic.

    Тот сжимал и хешировал 390 файлов на каждом запуске контейнера, а на
    четверти ядра это десятки секунд троттлинга — платформа не дожидалась
    готовности и убивала контейнер.
    """

    def test_admin_css_is_served(self):
        response = self.client.get("/static/admin/css/base.css")

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.getvalue()), 0)

    def test_admin_js_is_served(self):
        self.assertEqual(self.client.get("/static/admin/js/theme.js").status_code, 200)

    def test_missing_file_is_not_served(self):
        self.assertEqual(self.client.get("/static/admin/css/nope.css").status_code, 404)

    def test_login_page_opens(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)
