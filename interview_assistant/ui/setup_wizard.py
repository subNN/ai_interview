from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..core.audio import list_input_devices
from ..models import AppSettings, Secrets
from .widgets import DoubleSpinBox, SecretLineEdit, SpinBox


class SetupWizard(QWizard):
    def __init__(self, settings: AppSettings, secrets: Secrets, parent=None):
        super().__init__(parent)
        self._base_settings = settings
        self._base_secrets = secrets
        self.setWindowTitle("AI 面试助手设置")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(680, 560)
        self.setButtonText(QWizard.WizardButton.NextButton, "下一步")
        self.setButtonText(QWizard.WizardButton.BackButton, "上一步")
        self.setButtonText(QWizard.WizardButton.FinishButton, "完成并开始")
        self.setButtonText(QWizard.WizardButton.CancelButton, "稍后配置")
        self.addPage(self._build_audio_page())
        self.addPage(self._build_stt_page())
        self.addPage(self._build_llm_page())
        self.addPage(self._build_overlay_page())
        self._load(settings, secrets)

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[QWizardPage, QFormLayout]:
        page = QWizardPage()
        page.setTitle(title)
        page.setSubTitle(subtitle)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        layout.addLayout(form)
        layout.addStretch(1)
        return page, form

    def _build_audio_page(self) -> QWizardPage:
        page, form = self._page(
            "音频来源",
            "选择系统声音以监听面试官，或使用麦克风录制本地声音。",
        )
        self.audio_source = QComboBox()
        self.audio_source.addItem("系统声音（WASAPI Loopback）", "loopback")
        self.audio_source.addItem("麦克风", "mic")
        self.device = QComboBox()
        self.device.addItem("系统默认输入设备", None)
        for item in list_input_devices():
            self.device.addItem(item["name"], item["index"])
        form.addRow("音频来源", self.audio_source)
        form.addRow("麦克风设备", self.device)
        note = QLabel("系统声音模式会自动选择当前默认扬声器对应的 WASAPI Loopback 设备。")
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addRow("", note)
        return page

    def _build_stt_page(self) -> QWizardPage:
        page, form = self._page(
            "语音识别",
            "讯飞提供实时中文听写；也可以使用 OpenAI 或本地 Whisper。",
        )
        self.stt_provider = QComboBox()
        self.stt_provider.addItem("讯飞实时听写", "xunfei")
        self.stt_provider.addItem("OpenAI Whisper", "openai")
        self.stt_provider.addItem("本地 Whisper", "local")
        self.stt_language = QComboBox()
        self.stt_language.setEditable(True)
        self.stt_language.addItems(["zh", "en"])
        self.iflytek_app_id = QLineEdit()
        self.iflytek_key = SecretLineEdit()
        self.iflytek_secret = SecretLineEdit()
        self.openai_key = SecretLineEdit()
        form.addRow("识别服务", self.stt_provider)
        form.addRow("识别语言", self.stt_language)
        form.addRow("讯飞 App ID", self.iflytek_app_id)
        form.addRow("讯飞 API Key", self.iflytek_key)
        form.addRow("讯飞 Secret", self.iflytek_secret)
        form.addRow("OpenAI Key", self.openai_key)
        return page

    def _build_llm_page(self) -> QWizardPage:
        page, form = self._page(
            "AI 模型",
            "配置回答生成服务。DeepSeek 和 OpenAI 兼容接口均可使用。",
        )
        self.llm_provider = QComboBox()
        self.llm_provider.addItem("DeepSeek", "deepseek")
        self.llm_provider.addItem("OpenAI", "openai")
        self.llm_provider.addItem("OpenAI 兼容服务", "custom")
        self.llm_model = QLineEdit("deepseek-chat")
        self.llm_api_base = QLineEdit("https://api.deepseek.com")
        self.deepseek_key = SecretLineEdit()
        self.llm_temperature = DoubleSpinBox()
        self.llm_temperature.setRange(0, 2)
        self.llm_temperature.setSingleStep(0.1)
        form.addRow("模型供应商", self.llm_provider)
        form.addRow("模型名称", self.llm_model)
        form.addRow("API 地址", self.llm_api_base)
        form.addRow("DeepSeek Key", self.deepseek_key)
        form.addRow("回答温度", self.llm_temperature)
        return page

    def _build_overlay_page(self) -> QWizardPage:
        page, form = self._page(
            "悬浮阅读窗",
            "设置默认尺寸和阅读字号。运行时仍可拖动边框并调整透明度。",
        )
        self.overlay_font_size = SpinBox()
        self.overlay_font_size.setRange(16, 32)
        self.overlay_font_size.setSuffix(" px")
        self.overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity.setRange(65, 100)
        self.opacity_label = QLabel("96%")
        self.overlay_opacity.valueChanged.connect(
            lambda value: self.opacity_label.setText(f"{value}%")
        )
        self.always_on_top = QCheckBox("保持在其他窗口上方")
        form.addRow("回答字号", self.overlay_font_size)
        form.addRow("不透明度", self.overlay_opacity)
        form.addRow("", self.opacity_label)
        form.addRow("窗口层级", self.always_on_top)
        return page

    def _load(self, settings: AppSettings, secrets: Secrets):
        self.audio_source.setCurrentIndex(max(0, self.audio_source.findData(settings.audio_source)))
        if settings.audio_device is not None:
            index = self.device.findData(settings.audio_device)
            if index >= 0:
                self.device.setCurrentIndex(index)
        self.stt_provider.setCurrentIndex(max(0, self.stt_provider.findData(settings.stt_provider)))
        self.stt_language.setCurrentText(settings.stt_language)
        self.iflytek_app_id.setText(secrets.iflytek_app_id)
        self.iflytek_key.setText(secrets.iflytek_api_key)
        self.iflytek_secret.setText(secrets.iflytek_api_secret)
        self.openai_key.setText(secrets.openai_api_key)
        self.llm_provider.setCurrentIndex(max(0, self.llm_provider.findData(settings.llm_provider)))
        self.llm_model.setText(settings.llm_model)
        self.llm_api_base.setText(settings.llm_api_base)
        self.deepseek_key.setText(secrets.deepseek_api_key)
        self.llm_temperature.setValue(settings.llm_temperature)
        self.overlay_font_size.setValue(settings.overlay_font_size)
        self.overlay_opacity.setValue(round(settings.overlay_opacity * 100))
        self.opacity_label.setText(f"{round(settings.overlay_opacity * 100)}%")
        self.always_on_top.setChecked(settings.overlay_always_on_top)

    def values(self) -> tuple[AppSettings, Secrets]:
        settings = AppSettings.from_dict(self._base_settings.to_dict())
        settings.audio_source = self.audio_source.currentData()
        settings.audio_device = self.device.currentData()
        settings.stt_provider = self.stt_provider.currentData()
        settings.stt_language = self.stt_language.currentText().strip()
        settings.llm_provider = self.llm_provider.currentData()
        settings.llm_model = self.llm_model.text().strip()
        settings.llm_api_base = self.llm_api_base.text().strip()
        settings.llm_temperature = self.llm_temperature.value()
        settings.overlay_font_size = self.overlay_font_size.value()
        settings.overlay_opacity = self.overlay_opacity.value() / 100.0
        settings.overlay_always_on_top = self.always_on_top.isChecked()
        secrets = Secrets(
            deepseek_api_key=self.deepseek_key.text().strip(),
            openai_api_key=self.openai_key.text().strip(),
            iflytek_app_id=self.iflytek_app_id.text().strip(),
            iflytek_api_key=self.iflytek_key.text().strip(),
            iflytek_api_secret=self.iflytek_secret.text().strip(),
        )
        return settings.normalized(), secrets


    def validateCurrentPage(self) -> bool:
        page = self.currentId()
        if page == 1:
            provider = self.stt_provider.currentData()
            if provider == "xunfei" and not all(
                (
                    self.iflytek_app_id.text().strip(),
                    self.iflytek_key.text().strip(),
                    self.iflytek_secret.text().strip(),
                )
            ):
                QMessageBox.warning(self, "讯飞凭证不完整", "请填写完整的讯飞 App ID、API Key 和 Secret。")
                return False
            if provider == "openai" and not self.openai_key.text().strip():
                QMessageBox.warning(self, "缺少 OpenAI Key", "OpenAI 语音识别需要填写 OpenAI API Key。")
                return False
        if page == 2:
            provider = self.llm_provider.currentData()
            key = self.deepseek_key.text().strip() if provider == "deepseek" else self.openai_key.text().strip()
            if not key:
                QMessageBox.warning(self, "缺少 API Key", "请填写当前模型供应商对应的 API Key。")
                return False
        return True

    def accept(self):
        super().accept()
