#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arXiv论文搜索客户端
使用Python + PyQt5实现的GUI客户端，支持:
1. 服务器模式: 连接到arXiv搜索API服务器（可在配置处填入自己的服务器地址）
2. 本地模式: 直接使用arXiv官方API
"""

import sys
import os
import json
import csv
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QFormLayout, QGroupBox, QLabel, QLineEdit, QComboBox, QSpinBox, 
                           QPushButton, QTableView, QHeaderView, QAbstractItemView, 
                           QFileDialog, QMessageBox, QStatusBar, QMenu, QMenuBar, 
                           QAction, QActionGroup, QDialog, QDialogButtonBox, QTextEdit, QProgressBar,
                           QRadioButton, QButtonGroup, QInputDialog, QProgressDialog,
                           QCheckBox)
from PyQt5.QtCore import (Qt, QSettings, QDate, pyqtSlot, QUrl, QAbstractTableModel, 
                        QModelIndex, QVariant, QItemSelectionModel, QTimer, QProcess,
                        QSortFilterProxyModel)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtGui import QIcon, QTextCursor

class PaperModel(QAbstractTableModel):
    """论文数据模型，用于表格视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 初始化表头和数据
        self.headers = ["标题", "作者", "发布日期", "类别", "摘要"]
        self.papers = []
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """返回表头数据"""
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and section < len(self.headers):
            return self.headers[section]
        return QVariant()
    
    def rowCount(self, parent=QModelIndex()):
        """返回行数"""
        if parent.isValid():
            return 0
        return len(self.papers)
    
    def columnCount(self, parent=QModelIndex()):
        """返回列数"""
        if parent.isValid():
            return 0
        return len(self.headers)
    
    def data(self, index, role=Qt.DisplayRole):
        """返回单元格数据"""
        if not index.isValid() or index.row() >= len(self.papers):
            return QVariant()

        paper = self.papers[index.row()]
        
        if role == Qt.DisplayRole:
            column = index.column()
            if column == 0:  # 标题
                return paper.get("title", "")
                
            elif column == 1:  # 作者
                authors = paper.get("authors", [])
                return ", ".join(authors)
                
            elif column == 2:  # 发布日期
                return paper.get("published", "")
                
            elif column == 3:  # 类别
                categories = paper.get("categories", [])
                return ", ".join(categories)
                
            elif column == 4:  # 摘要
                summary = paper.get("summary", "")
                # 截断过长的摘要
                if len(summary) > 150:
                    return summary[:150] + "..."
                return summary
        
        # 工具提示显示完整摘要
        if role == Qt.ToolTipRole and index.column() == 4:
            return paper.get("summary", "")
        
        return QVariant()
    
    def set_papers(self, papers):
        """设置论文数据"""
        self.beginResetModel()
        self.papers = papers
        self.endResetModel()
    
    def clear_papers(self):
        """清除所有论文数据"""
        self.beginResetModel()
        self.papers = []
        self.endResetModel()
    
    def get_paper(self, row):
        """获取指定行的论文"""
        if 0 <= row < len(self.papers):
            return self.papers[row]
        return {}
    
    def get_all_papers(self):
        """获取所有论文"""
        return self.papers
    
    def get_selected_papers(self, selection_model):
        """获取所有选中的论文"""
        selected_papers = []
        
        if not selection_model:
            return selected_papers
        
        for index in selection_model.selectedRows():
            if index.isValid() and index.row() < len(self.papers):
                selected_papers.append(self.papers[index.row()])
        
        return selected_papers
    
    def sort_papers(self, column, order=Qt.AscendingOrder):
        """按照指定列排序论文列表"""
        self.beginResetModel()
        
        if column == 0:  # 按标题排序
            self.papers = sorted(
                self.papers, 
                key=lambda p: p.get("title", "").lower(),
                reverse=(order == Qt.DescendingOrder)
            )
        elif column == 2:  # 按发布日期排序
            self.papers = sorted(
                self.papers, 
                key=lambda p: p.get("published", ""),
                reverse=(order == Qt.DescendingOrder)
            )
        
        self.endResetModel()


class NetworkTestDialog(QDialog):
    """网络连接测试对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("网络连接测试")
        self.resize(500, 400)
        self.setup_ui()
        
        # 初始化网络管理器
        self.network_manager = QNetworkAccessManager()
        self.ping_process = None
        
        # 加载保存的设置
        self.load_servers()
    
    def setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)
        
        # 服务器配置组
        server_group = QGroupBox("服务器配置")
        server_layout = QFormLayout()
        
        # 服务器URL输入（需要的话可配置自己的服务器URL）
        self.server_url_edit = QLineEdit()
        self.server_url_edit.setPlaceholderText("http://127.0.0.1:5000")  # 你的服务器地址
        server_layout.addRow("服务器URL:", self.server_url_edit)
        
        # API密钥输入（需要的话可配置自己的API Key）
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("您的API密钥")
        server_layout.addRow("API密钥:", self.api_key_edit)
        
        # 保存的服务器选择
        self.server_combo = QComboBox()
        self.server_combo.setMinimumWidth(200)
        self.server_combo.currentIndexChanged.connect(self.on_server_selected)
        server_layout.addRow("保存的服务器:", self.server_combo)
        
        # 添加保存按钮
        save_layout = QHBoxLayout()
        self.save_button = QPushButton("保存当前配置")
        self.save_button.clicked.connect(self.save_current_server)
        self.delete_button = QPushButton("删除选中配置")
        self.delete_button.clicked.connect(self.delete_selected_server)
        save_layout.addWidget(self.save_button)
        save_layout.addWidget(self.delete_button)
        server_layout.addRow("", save_layout)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # 测试类型选择
        test_group = QGroupBox("测试类型")
        test_layout = QVBoxLayout()
        
        # 创建单选按钮
        self.ping_radio = QRadioButton("Ping测试")
        self.api_radio = QRadioButton("API连接测试")
        self.ping_radio.setChecked(True)
        
        test_layout.addWidget(self.ping_radio)
        test_layout.addWidget(self.api_radio)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        # 测试结果显示
        result_group = QGroupBox("测试结果")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        
        result_layout.addWidget(self.result_text)
        result_layout.addWidget(self.progress_bar)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 测试按钮
        self.test_button = QPushButton("开始测试")
        self.test_button.clicked.connect(self.start_test)
        
        # 使用此配置按钮
        self.use_button = QPushButton("使用此配置")
        self.use_button.clicked.connect(self.accept)
        
        # 取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.test_button)
        button_layout.addWidget(self.use_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def load_servers(self):
        """加载保存的服务器配置"""
        settings = QSettings("arXivSearchClient", "Config")
        
        # 加载当前配置（默认改为示例地址）
        self.server_url_edit.setText(settings.value("serverUrl", "http://127.0.0.1:5000"))
        self.api_key_edit.setText(settings.value("apiKey", "your_secret_api_key"))
        
        # 加载保存的服务器列表
        servers = settings.value("savedServers", [])
        self.server_combo.clear()
        
        # 添加默认选项
        self.server_combo.addItem("-- 选择保存的服务器 --")
        
        if servers:
            for server in servers:
                self.server_combo.addItem(server["name"], server)
    
    def on_server_selected(self, index):
        """当选择保存的服务器时更新输入框"""
        if index <= 0:  # 跳过默认选项
            return
            
        server_data = self.server_combo.itemData(index)
        if server_data:
            self.server_url_edit.setText(server_data["url"])
            self.api_key_edit.setText(server_data["key"])
    
    def save_current_server(self):
        """保存当前服务器配置"""
        url = self.server_url_edit.text().strip()
        key = self.api_key_edit.text().strip()
        
        if not url:
            QMessageBox.warning(self, "错误", "请输入服务器URL")
            return
            
        # 请求保存名称
        name, ok = QInputDialog.getText(
            self, "保存服务器配置", 
            "请输入此配置的名称:",
            QLineEdit.Normal
        )
        
        if not ok or not name:
            return
            
        # 保存到设置
        settings = QSettings("arXivSearchClient", "Config")
        servers = settings.value("savedServers", [])
        
        # 创建新的服务器配置
        new_server = {
            "name": name,
            "url": url,
            "key": key
        }
        
        # 检查是否已存在同名配置
        for i, server in enumerate(servers):
            if server["name"] == name:
                # 替换现有配置
                servers[i] = new_server
                settings.setValue("savedServers", servers)
                self.load_servers()
                QMessageBox.information(self, "保存成功", f"已更新配置: {name}")
                return
        
        # 添加新配置
        servers.append(new_server)
        settings.setValue("savedServers", servers)
        
        # 重新加载列表
        self.load_servers()
        QMessageBox.information(self, "保存成功", f"已保存配置: {name}")
    
    def delete_selected_server(self):
        """删除选中的服务器配置"""
        index = self.server_combo.currentIndex()
        if index <= 0:
            QMessageBox.warning(self, "错误", "请先选择一个保存的配置")
            return
            
        server_name = self.server_combo.currentText()
        
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除配置 '{server_name}' 吗?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # 从设置中删除
        settings = QSettings("arXivSearchClient", "Config")
        servers = settings.value("savedServers", [])
        
        servers = [s for s in servers if s["name"] != server_name]
        settings.setValue("savedServers", servers)
        
        # 重新加载列表
        self.load_servers()
        QMessageBox.information(self, "删除成功", f"已删除配置: {server_name}")
    
    def start_test(self):
        """开始网络测试"""
        url = self.server_url_edit.text().strip()
        
        if not url:
            QMessageBox.warning(self, "错误", "请输入服务器URL")
            return
            
        # 清除之前的结果
        self.result_text.clear()
        self.test_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # 分析URL
        try:
            qurl = QUrl(url)
            host = qurl.host()
            port = qurl.port(80 if qurl.scheme() == "http" else 443)
            
            self.append_result(f"测试服务器: {url}")
            self.append_result(f"主机: {host}")
            self.append_result(f"端口: {port}")
            self.append_result("-" * 40)
            
            if self.ping_radio.isChecked():
                self.run_ping_test(host)
            else:
                # 不再测试/test端点，而是测试服务器是否可访问
                if "arxiv.org" in host:
                    self.run_arxiv_api_test()
                else:
                    self.run_server_availability_test(url)
                
        except Exception as e:
            self.append_result(f"错误: {str(e)}")
            self.test_button.setEnabled(True)
            self.progress_bar.setVisible(False)
    
    def run_ping_test(self, host):
        """执行Ping测试"""
        self.append_result(f"开始Ping测试 {host}...")
        self.progress_bar.setValue(10)
        
        # 使用QProcess代替线程，避免多线程问题
        try:
            # 根据操作系统确定ping命令
            if sys.platform == "win32":
                cmd = ["ping", "-n", "4", host]
            else:
                cmd = ["ping", "-c", "4", host]
            
            # 创建进程但暂不启动
            self.ping_process = QProcess()
            self.ping_process.setProcessChannelMode(QProcess.MergedChannels)
            
            # 连接信号
            self.ping_process.readyReadStandardOutput.connect(self.read_ping_output)
            self.ping_process.finished.connect(self.ping_process_finished)
            
            # 启动进程
            self.append_result(f"执行命令: {' '.join(cmd)}")
            self.ping_process.start(cmd[0], cmd[1:])
            
        except Exception as e:
            self.append_result(f"Ping测试出错: {str(e)}")
            self.progress_bar.setValue(100)
            self.progress_bar.setVisible(False)
            self.test_button.setEnabled(True)
    
    def read_ping_output(self):
        """读取ping命令的输出"""
        data = self.ping_process.readAllStandardOutput()
        text = bytes(data).decode(errors='replace')
        self.append_result(text.strip())
        
        # 更新进度条
        current = self.progress_bar.value()
        if current < 90:
            self.progress_bar.setValue(current + 10)
    
    def ping_process_finished(self, exitCode, exitStatus):
        """ping进程完成时调用"""
        if exitCode == 0:
            self.append_result("Ping测试成功完成!")
        else:
            self.append_result(f"Ping测试失败，退出代码: {exitCode}")
        
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.test_button.setEnabled(True)
    
    def run_arxiv_api_test(self):
        """测试arXiv官方API连接"""
        self.append_result("开始测试arXiv官方API连接...")
        
        test_url = "http://export.arxiv.org/api/query?search_query=all:electron&start=0&max_results=1"
        request = QNetworkRequest(QUrl(test_url))
        
        self.append_result(f"测试URL: {test_url}")
        self.progress_bar.setValue(20)
        
        # 发送请求
        reply = self.network_manager.get(request)
        
        # 更新进度条
        def update_progress():
            if self.progress_bar.value() < 90:
                self.progress_bar.setValue(self.progress_bar.value() + 10)
        
        timer = QTimer(self)
        timer.timeout.connect(update_progress)
        timer.start(300)
        
        def handle_reply():
            timer.stop()
            self.progress_bar.setValue(100)
            
            if reply.error() == QNetworkReply.NoError:
                self.append_result("arXiv API连接成功!")
                
                # 解析响应
                data = reply.readAll().data()
                self.append_result(f"收到响应，长度: {len(data)} 字节")
                
                # 检查响应是否包含XML
                if b"<entry>" in data:
                    self.append_result("API返回了有效的XML响应，连接测试成功")
                else:
                    self.append_result(f"收到非XML响应: {data[:100].decode()}...")
            else:
                error_msg = reply.errorString()
                self.append_result(f"arXiv API连接错误: {error_msg}")
            
            self.progress_bar.setVisible(False)
            self.test_button.setEnabled(True)
            reply.deleteLater()
        
        reply.finished.connect(handle_reply)
    
    def run_server_availability_test(self, url):
        """测试服务器可用性，而不是特定端点"""
        self.append_result("开始测试服务器可用性...")
        
        # 创建一个基本请求到服务器根路径
        base_url = url.split('/')[0] + '//' + url.split('/')[2]
        request = QNetworkRequest(QUrl(base_url))
        
        self.append_result(f"测试URL: {base_url}")
        self.progress_bar.setValue(20)
        
        # 发送请求
        reply = self.network_manager.get(request)
        
        # 更新进度条
        def update_progress():
            if self.progress_bar.value() < 90:
                self.progress_bar.setValue(self.progress_bar.value() + 10)
        
        timer = QTimer(self)
        timer.timeout.connect(update_progress)
        timer.start(300)
        
        def handle_reply():
            timer.stop()
            self.progress_bar.setValue(100)
            
            if reply.error() == QNetworkReply.NoError:
                self.append_result("服务器连接成功!")
                self.append_result("服务器可访问，但未检查特定API端点")
            else:
                error_msg = reply.errorString()
                self.append_result(f"服务器连接错误: {error_msg}")
                
                if "Connection refused" in error_msg:
                    self.append_result("\n可能的原因:")
                    self.append_result("1. 服务器未运行")
                    self.append_result("2. 端口号错误或端口未开放")
                    self.append_result("3. 防火墙阻止了连接")
            
            self.progress_bar.setVisible(False)
            self.test_button.setEnabled(True)
            reply.deleteLater()
    
    def append_result(self, text):
        """向结果文本框添加文本"""
        self.result_text.moveCursor(QTextCursor.End)
        self.result_text.insertPlainText(text + "\n")
        self.result_text.moveCursor(QTextCursor.End)
        QApplication.processEvents()  # 更新UI
    
    def get_server_url(self):
        """获取服务器URL"""
        return self.server_url_edit.text()
    
    def get_api_key(self):
        """获取API密钥"""
        return self.api_key_edit.text()


class ConfigDialog(QDialog):
    """配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        """设置用户界面"""
        # 设置窗口标题
        self.setWindowTitle("网络环境配置")
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 模式选择组
        mode_group = QGroupBox("运行模式")
        mode_layout = QVBoxLayout()
        
        # 模式单选按钮
        self.direct_arxiv_radio = QRadioButton("直接访问arXiv模式 (不需要自建服务器)")
        self.server_radio = QRadioButton("服务器模式 (使用自建arXiv搜索API服务器)")
        
        self.direct_arxiv_radio.setToolTip("直接使用arXiv官方API，无需额外服务器")
        self.server_radio.setToolTip("使用您自建的arXiv搜索API服务器")
        
        mode_layout.addWidget(self.direct_arxiv_radio)
        mode_layout.addWidget(self.server_radio)
        
        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)
        
        # 网络环境选择组 (仅在服务器模式下有效)
        self.network_group = QGroupBox("网络环境选择 (服务器模式)")
        network_layout = QVBoxLayout()
        
        # 网络环境单选按钮
        self.local_network_radio = QRadioButton("本地网络 (局域网环境)")
        self.external_network_radio = QRadioButton("外部网络 (公网环境)")
        
        network_layout.addWidget(self.local_network_radio)
        network_layout.addWidget(self.external_network_radio)
        
        self.network_group.setLayout(network_layout)
        main_layout.addWidget(self.network_group)
        
        # 服务器配置组 - 本地网络
        self.local_server_group = QGroupBox("本地网络服务器配置")
        local_server_layout = QFormLayout()
        
        # 本地服务器URL（需要的话可配置自己的局域网服务器地址）
        self.local_server_url_edit = QLineEdit(self)
        self.local_server_url_edit.setPlaceholderText("http://127.0.0.1:5000")
        local_server_layout.addRow("服务器URL:", self.local_server_url_edit)
        
        # 本地服务器API密钥
        self.local_api_key_edit = QLineEdit(self)
        self.local_api_key_edit.setEchoMode(QLineEdit.Password)
        self.local_api_key_edit.setPlaceholderText("您的API密钥")
        local_server_layout.addRow("API密钥:", self.local_api_key_edit)
        
        # 测试本地连接按钮
        self.test_local_button = QPushButton("测试本地连接")
        self.test_local_button.clicked.connect(lambda: self.test_connection("local"))
        local_server_layout.addRow("", self.test_local_button)
        
        self.local_server_group.setLayout(local_server_layout)
        main_layout.addWidget(self.local_server_group)
        
        # 服务器配置组 - 外部网络
        self.external_server_group = QGroupBox("外部网络服务器配置")
        external_server_layout = QFormLayout()
        
        # 外部服务器URL（需要的话可配置自己公网服务器地址）
        self.external_server_url_edit = QLineEdit(self)
        self.external_server_url_edit.setPlaceholderText("http://example.com:80")
        external_server_layout.addRow("服务器URL:", self.external_server_url_edit)
        
        # 外部服务器API密钥
        self.external_api_key_edit = QLineEdit(self)
        self.external_api_key_edit.setEchoMode(QLineEdit.Password)
        self.external_api_key_edit.setPlaceholderText("您的API密钥")
        external_server_layout.addRow("API密钥:", self.external_api_key_edit)
        
        # 连接超时
        self.timeout_spinbox = QSpinBox(self)
        self.timeout_spinbox.setRange(5, 120)
        self.timeout_spinbox.setSuffix(" 秒")
        external_server_layout.addRow("连接超时:", self.timeout_spinbox)
        
        # 测试外部连接按钮
        self.test_external_button = QPushButton("测试外部连接")
        self.test_external_button.clicked.connect(lambda: self.test_connection("external"))
        external_server_layout.addRow("", self.test_external_button)
        
        self.external_server_group.setLayout(external_server_layout)
        main_layout.addWidget(self.external_server_group)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, 
            Qt.Horizontal, 
            self
        )
        
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("确定")
        
        self.cancel_button = button_box.button(QDialogButtonBox.Cancel)
        self.cancel_button.setText("取消")
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)
        
        self.setLayout(main_layout)
        self.resize(450, 600)
        
        # 连接信号
        self.direct_arxiv_radio.toggled.connect(self.toggle_mode_controls)
        self.server_radio.toggled.connect(self.toggle_mode_controls)
        self.local_network_radio.toggled.connect(self.toggle_server_controls)
    
    def toggle_mode_controls(self, checked):
        """根据模式选择启用/禁用网络环境和服务器控件"""
        is_server_mode = self.server_radio.isChecked()
        self.network_group.setEnabled(is_server_mode)
        self.local_server_group.setEnabled(is_server_mode and self.local_network_radio.isChecked())
        self.external_server_group.setEnabled(is_server_mode and self.external_network_radio.isChecked())
    
    def toggle_server_controls(self, use_local_network):
        """根据网络环境选项启用/禁用服务器配置控件"""
        if self.server_radio.isChecked():
            self.local_server_group.setEnabled(use_local_network)
            self.external_server_group.setEnabled(not use_local_network)
    
    def load_settings(self):
        """从设置加载配置"""
        settings = QSettings("arXivSearchClient", "Config")
        
        # 加载模式设置
        use_direct_arxiv = settings.value("useDirectArxiv", False, type=bool)
        if use_direct_arxiv:
            self.direct_arxiv_radio.setChecked(True)
        else:
            self.server_radio.setChecked(True)
        
        # 加载网络环境设置
        use_local_network = settings.value("useLocalNetwork", False, type=bool)
        if use_local_network:
            self.local_network_radio.setChecked(True)
        else:
            self.external_network_radio.setChecked(True)
        
        # 加载本地服务器设置
        self.local_server_url_edit.setText(settings.value("localServerUrl", "http://127.0.0.1:5000"))
        self.local_api_key_edit.setText(settings.value("localApiKey", "your_secret_api_key"))
        
        # 加载外部服务器设置
        self.external_server_url_edit.setText(settings.value("externalServerUrl", "http://example.com:80"))
        self.external_api_key_edit.setText(settings.value("externalApiKey", "your_secret_api_key"))
        self.timeout_spinbox.setValue(int(settings.value("connectionTimeout", 30)))
        
        # 启用/禁用控件
        self.toggle_mode_controls(True)
        self.toggle_server_controls(use_local_network)
    
    def use_direct_arxiv(self):
        """获取是否直接使用arXiv API"""
        return self.direct_arxiv_radio.isChecked()
    
    def use_local_network(self):
        """获取是否使用本地网络"""
        return self.local_network_radio.isChecked()
    
    def get_active_server_url(self):
        """获取当前激活的服务器URL"""
        if self.use_direct_arxiv():
            return "https://export.arxiv.org/api/query"
            
        if self.use_local_network():
            return self.local_server_url_edit.text()
        else:
            return self.external_server_url_edit.text()
    
    def get_active_api_key(self):
        """获取当前激活的API密钥"""
        if self.use_direct_arxiv():
            return ""
            
        if self.use_local_network():
            return self.local_api_key_edit.text()
        else:
            return self.external_api_key_edit.text()
    
    def connection_timeout(self):
        """获取连接超时"""
        return self.timeout_spinbox.value()
    
    def test_connection(self, mode):
        """测试服务器连接"""
        network_test = NetworkTestDialog(self)
        
        if mode == "local":
            network_test.server_url_edit.setText(self.local_server_url_edit.text())
            network_test.api_key_edit.setText(self.local_api_key_edit.text())
        else:
            network_test.server_url_edit.setText(self.external_server_url_edit.text())
            network_test.api_key_edit.setText(self.external_api_key_edit.text())
        
        # 如果测试成功并用户选择使用该配置
        if network_test.exec_() == QDialog.Accepted:
            new_url = network_test.get_server_url()
            new_key = network_test.get_api_key()
            
            if mode == "local":
                self.local_server_url_edit.setText(new_url)
                self.local_api_key_edit.setText(new_key)
            else:
                self.external_server_url_edit.setText(new_url)
                self.external_api_key_edit.setText(new_key)
    
    def accept(self):
        """确定按钮处理"""
        # 保存设置
        settings = QSettings("arXivSearchClient", "Config")
        settings.setValue("useDirectArxiv", self.use_direct_arxiv())
        settings.setValue("useLocalNetwork", self.use_local_network())
        settings.setValue("localServerUrl", self.local_server_url_edit.text())
        settings.setValue("localApiKey", self.local_api_key_edit.text())
        settings.setValue("externalServerUrl", self.external_server_url_edit.text())
        settings.setValue("externalApiKey", self.external_api_key_edit.text())
        settings.setValue("connectionTimeout", self.timeout_spinbox.value())
        
        # 设置当前活动的服务器
        settings.setValue("serverUrl", self.get_active_server_url())
        settings.setValue("apiKey", self.get_active_api_key())
        
        super().accept()


class MainWindow(QMainWindow):
    """arXiv论文搜索工具主窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 初始化网络管理器和数据模型
        self.network_manager = QNetworkAccessManager()
        self.table_model = PaperModel()
        self.papers = []
        
        # 加载配置
        self.load_config()
        
        # 设置UI
        self.setup_ui()
        
        # 连接信号
        self.connect_signals()
        
        # 设置窗口标题和大小
        self.setWindowTitle("arXiv论文搜索工具")
        self.resize(900, 600)
    
    def load_config(self):
        """从设置加载配置"""
        settings = QSettings("arXivSearchClient", "Config")
        
        # 如果需要配置自己的服务器，请将默认值改为你自己的地址
        self.server_url = settings.value("serverUrl", "http://127.0.0.1:5000")
        self.api_key = settings.value("apiKey", "your_secret_api_key")
        self.use_direct_arxiv = settings.value("useDirectArxiv", False, type=bool)
        self.use_local_network = settings.value("useLocalNetwork", False, type=bool)
        
        # 加载详细的网络环境配置
        self.local_server_url = settings.value("localServerUrl", "http://127.0.0.1:5000")
        self.local_api_key = settings.value("localApiKey", "your_secret_api_key")
        self.external_server_url = settings.value("externalServerUrl", "http://example.com:80")
        self.external_api_key = settings.value("externalApiKey", "your_secret_api_key")
        
        if self.use_direct_arxiv:
            self.server_url = "https://export.arxiv.org/api/query"
            self.api_key = ""
    
    def setup_ui(self):
        """设置用户界面"""
        # 创建中央部件和主布局
        central_widget = QWidget(self)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建菜单
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu("文件")
        tools_menu = menu_bar.addMenu("工具")
        mode_menu = menu_bar.addMenu("运行模式")
        help_menu = menu_bar.addMenu("帮助")
        
        # 添加菜单动作
        settings_action = file_menu.addAction("设置")
        exit_action = file_menu.addAction("退出")
        
        # 添加工具菜单项
        network_test_action = tools_menu.addAction("网络连接测试")
        
        # 添加模式菜单项
        self.direct_arxiv_action = mode_menu.addAction("直接访问arXiv模式")
        self.direct_arxiv_action.setCheckable(True)
        self.direct_arxiv_action.setChecked(self.use_direct_arxiv)
        
        self.server_action = mode_menu.addAction("服务器模式")
        self.server_action.setCheckable(True)
        self.server_action.setChecked(not self.use_direct_arxiv)
        
        # 确保总是只有一个选中
        self.mode_action_group = QActionGroup(self)
        self.mode_action_group.addAction(self.direct_arxiv_action)
        self.mode_action_group.addAction(self.server_action)
        self.mode_action_group.setExclusive(True)
        
        # 添加服务器环境菜单项(仅在服务器模式下有效)
        self.network_menu = menu_bar.addMenu("网络环境")
        
        self.use_local_action = self.network_menu.addAction("使用本地网络")
        self.use_local_action.setCheckable(True)
        self.use_local_action.setChecked(self.use_local_network)
        
        self.use_external_action = self.network_menu.addAction("使用外部网络")
        self.use_external_action.setCheckable(True)
        self.use_external_action.setChecked(not self.use_local_network)
        
        # 确保总是只有一个选中
        self.network_action_group = QActionGroup(self)
        self.network_action_group.addAction(self.use_local_action)
        self.network_action_group.addAction(self.use_external_action)
        self.network_action_group.setExclusive(True)
        
        # 设置网络环境菜单在服务器模式下才启用
        self.network_menu.setEnabled(not self.use_direct_arxiv)
        
        about_action = help_menu.addAction("关于")
        
        # 连接菜单动作
        settings_action.triggered.connect(self.open_settings)
        exit_action.triggered.connect(self.close)
        network_test_action.triggered.connect(self.open_network_test)
        self.direct_arxiv_action.triggered.connect(lambda: self.switch_mode(True))
        self.server_action.triggered.connect(lambda: self.switch_mode(False))
        self.use_local_action.triggered.connect(lambda: self.switch_network_environment(True))
        self.use_external_action.triggered.connect(lambda: self.switch_network_environment(False))
        about_action.triggered.connect(self.show_about)
        
        self.setMenuBar(menu_bar)
        
        # 模式显示
        mode_layout = QHBoxLayout()
        self.mode_label = QLabel("当前模式:")
        self.mode_value = QLabel("直接访问arXiv" if self.use_direct_arxiv else "服务器模式")
        self.mode_value.setStyleSheet("font-weight: bold; color: #0066cc;")
        mode_layout.addWidget(self.mode_label)
        mode_layout.addWidget(self.mode_value)
        
        # 添加服务器URL显示
        self.server_label = QLabel("网络环境:")
        self.server_value = QLabel("本地网络" if self.use_local_network else "外部网络")
        self.server_url_label = QLabel(f"服务器: {self.server_url}")
        
        # 仅在服务器模式下显示网络环境
        self.server_label.setVisible(not self.use_direct_arxiv)
        self.server_value.setVisible(not self.use_direct_arxiv)
        
        mode_layout.addWidget(self.server_label)
        mode_layout.addWidget(self.server_value)
        mode_layout.addWidget(self.server_url_label)
        
        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)
        
        # 搜索参数分组
        search_group = QGroupBox("搜索参数")
        form_layout = QFormLayout(search_group)
        
        # 关键词输入
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("输入搜索关键词，用空格分隔")
        form_layout.addRow("关键词:", self.keywords_edit)
        
        # 搜索模式选择
        self.search_mode_combo = QComboBox()
        self.search_mode_combo.addItem("精确匹配 (AND)", "precise")
        self.search_mode_combo.addItem("模糊匹配 (OR)", "fuzzy")
        self.search_mode_combo.setToolTip("精确匹配：关键词必须同时出现在标题和摘要中\n模糊匹配：关键词可以出现在标题或摘要中")
        form_layout.addRow("搜索模式:", self.search_mode_combo)
        
        # 开始年份
        self.start_year_spin = QSpinBox()
        self.start_year_spin.setRange(1900, QDate.currentDate().year())
        self.start_year_spin.setValue(2010)
        self.start_year_spin.setSpecialValueText("不限")
        form_layout.addRow("开始年份:", self.start_year_spin)
        
        # 结束年份
        self.end_year_spin = QSpinBox()
        self.end_year_spin.setRange(1900, QDate.currentDate().year())
        self.end_year_spin.setValue(QDate.currentDate().year())
        self.end_year_spin.setSpecialValueText("不限")
        form_layout.addRow("结束年份:", self.end_year_spin)
        
        # 最大结果数
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 1000)
        self.max_results_spin.setValue(100)
        form_layout.addRow("最大结果数:", self.max_results_spin)
        
        # 搜索按钮
        self.search_button = QPushButton("搜索")
        form_layout.addRow("", self.search_button)
        
        main_layout.addWidget(search_group)
        
        # 排序控件
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("排序方式:"))
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("默认排序", None)
        self.sort_combo.addItem("按标题排序", 0)
        self.sort_combo.addItem("按日期排序", 2)
        sort_layout.addWidget(self.sort_combo)
        
        self.sort_order_button = QPushButton("↑")
        self.sort_order_button.setCheckable(True)
        self.sort_order_button.setFixedWidth(30)
        self.sort_order_button.setToolTip("切换排序顺序")
        sort_layout.addWidget(self.sort_order_button)
        
        sort_layout.addStretch()
        main_layout.addLayout(sort_layout)
        
        # 结果表格
        self.results_table = QTableView()
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.results_table.setModel(self.table_model)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        main_layout.addWidget(self.results_table)
        
        # 操作按钮
        action_layout = QHBoxLayout()
        
        self.download_button = QPushButton("下载选中论文")
        self.csv_button = QPushButton("导出为CSV")
        self.text_button = QPushButton("保存为文本")
        self.settings_button = QPushButton("设置")
        self.network_test_button = QPushButton("网络测试")
        
        action_layout.addWidget(self.download_button)
        action_layout.addWidget(self.csv_button)
        action_layout.addWidget(self.text_button)
        action_layout.addWidget(self.settings_button)
        action_layout.addWidget(self.network_test_button)
        
        main_layout.addLayout(action_layout)
        
        # 状态栏
        status_bar = QStatusBar(self)
        self.status_label = QLabel("就绪")
        status_bar.addWidget(self.status_label)
        self.setStatusBar(status_bar)
        
        # 设置中央部件
        self.setCentralWidget(central_widget)
    
    def connect_signals(self):
        """连接各种信号和槽"""
        self.search_button.clicked.connect(self.search_papers)
        self.download_button.clicked.connect(self.download_selected)
        self.csv_button.clicked.connect(self.save_to_csv)
        self.text_button.clicked.connect(self.save_to_text)
        self.settings_button.clicked.connect(self.open_settings)
        self.network_test_button.clicked.connect(self.open_network_test)
        
        # 排序功能
        self.sort_combo.currentIndexChanged.connect(self.sort_papers)
        self.sort_order_button.toggled.connect(self.toggle_sort_order)
        
        # 让回车键触发搜索
        self.keywords_edit.returnPressed.connect(self.search_papers)
    
    def sort_papers(self):
        """根据当前排序设置对论文进行排序"""
        sort_column = self.sort_combo.currentData()
        if sort_column is None:
            return  # 默认排序，不做处理
        
        sort_order = Qt.DescendingOrder if self.sort_order_button.isChecked() else Qt.AscendingOrder
        self.table_model.sort_papers(sort_column, sort_order)
    
    def toggle_sort_order(self, checked):
        """切换排序顺序"""
        self.sort_order_button.setText("↓" if checked else "↑")
        if self.sort_combo.currentData() is not None:
            self.sort_papers()  # 重新排序
    
    def switch_mode(self, use_direct_arxiv):
        """切换运行模式"""
        if self.use_direct_arxiv == use_direct_arxiv:
            return
            
        self.use_direct_arxiv = use_direct_arxiv
        
        # 更新UI显示
        self.mode_value.setText("直接访问arXiv" if use_direct_arxiv else "服务器模式")
        
        # 显示/隐藏网络环境控件
        self.server_label.setVisible(not use_direct_arxiv)
        self.server_value.setVisible(not use_direct_arxiv)
        self.network_menu.setEnabled(not use_direct_arxiv)
        
        # 设置当前活动的服务器
        if use_direct_arxiv:
            self.server_url = "https://export.arxiv.org/api/query"
            self.api_key = ""
        else:
            if self.use_local_network:
                self.server_url = self.local_server_url
                self.api_key = self.local_api_key
            else:
                self.server_url = self.external_server_url
                self.api_key = self.external_api_key
            
        # 更新显示的服务器URL
        self.server_url_label.setText(f"服务器: {self.server_url}")
        
        # 保存当前设置
        settings = QSettings("arXivSearchClient", "Config")
        settings.setValue("useDirectArxiv", use_direct_arxiv)
        settings.setValue("serverUrl", self.server_url)
        settings.setValue("apiKey", self.api_key)
        
        self.status_label.setText(f"已切换到{'直接访问arXiv' if use_direct_arxiv else '服务器'}模式")
    
    def switch_network_environment(self, use_local_network):
        """切换网络环境（仅在服务器模式下有效）"""
        if self.use_direct_arxiv or self.use_local_network == use_local_network:
            return
            
        self.use_local_network = use_local_network
        
        # 更新UI显示
        self.server_value.setText("本地网络" if use_local_network else "外部网络")
        
        # 设置当前活动的服务器
        if use_local_network:
            self.server_url = self.local_server_url
            self.api_key = self.local_api_key
        else:
            self.server_url = self.external_server_url
            self.api_key = self.external_api_key
            
        # 更新显示的服务器URL
        self.server_url_label.setText(f"服务器: {self.server_url}")
        
        # 保存当前设置
        settings = QSettings("arXivSearchClient", "Config")
        settings.setValue("useLocalNetwork", use_local_network)
        settings.setValue("serverUrl", self.server_url)
        settings.setValue("apiKey", self.api_key)
        
        self.status_label.setText(f"已切换到{'本地' if use_local_network else '外部'}网络环境")
    
    def create_request(self, endpoint):
        """创建网络请求"""
        request = QNetworkRequest(QUrl(self.server_url + endpoint))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        if self.api_key:
            request.setRawHeader(b"X-API-Key", self.api_key.encode())
        return request
    
    def search_papers(self):
        """搜索论文"""
        # 准备UI进行搜索
        self.search_button.setEnabled(False)
        self.table_model.clear_papers()
        
        # 获取搜索参数
        keywords = self.keywords_edit.text()
        if not keywords:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            self.search_button.setEnabled(True)
            return
            
        search_mode = self.search_mode_combo.currentData()
        max_results = self.max_results_spin.value()
        
        # 获取年份(如果选择了"不限"则传递None)
        start_year = None
        if self.start_year_spin.value() != self.start_year_spin.minimum():
            start_year = self.start_year_spin.value()
            
        end_year = None
        if self.end_year_spin.value() != self.end_year_spin.minimum():
            end_year = self.end_year_spin.value()
        
        # 设置状态
        if self.use_direct_arxiv:
            self.status_label.setText("正在直接访问arXiv API搜索...")
            self.search_via_arxiv_api(keywords, search_mode, start_year, end_year, max_results)
        else:
            network_type = "本地" if self.use_local_network else "外部"
            self.status_label.setText(f"正在通过{network_type}网络搜索...")
            self.search_via_server(keywords, search_mode, start_year, end_year, max_results)
    
    def search_via_arxiv_api(self, keywords, search_mode, start_year, end_year, max_results):
        """通过arXiv官方API搜索"""
        # 构建查询参数
        query_terms = keywords.split()
        if search_mode == "precise":
            # 精确模式使用AND连接关键词
            query = " AND ".join([f'all:"{term}"' for term in query_terms])
        else:
            # 模糊模式使用OR连接关键词
            query = " OR ".join([f'all:"{term}"' for term in query_terms])
            
        # 添加年份过滤
        if start_year and end_year:
            query += f" AND submittedDate:[{start_year}0101 TO {end_year}1231]"
        elif start_year:
            query += f" AND submittedDate:[{start_year}0101 TO 99991231]"
        elif end_year:
            query += f" AND submittedDate:[00010101 TO {end_year}1231]"
            
        # 构建API请求URL
        base_url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        query_string = urllib.parse.urlencode(params)
        request_url = f"{base_url}?{query_string}"
        
        # 创建请求
        request = QNetworkRequest(QUrl(request_url))
        
        # 发送请求
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self.handle_arxiv_api_reply(reply))
    
    def handle_arxiv_api_reply(self, reply):
        """处理arXiv API的响应"""
        self.search_button.setEnabled(True)
        
        if reply.error() == QNetworkReply.NoError:
            # 解析XML响应
            try:
                data = reply.readAll().data()
                self.parse_arxiv_api_response(data)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"解析arXiv API响应时出错: {str(e)}")
                self.status_label.setText("解析响应失败")
        else:
            # 处理错误
            self.handle_network_error(reply.error())
        
        # 释放资源
        reply.deleteLater()
    
    def parse_arxiv_api_response(self, xml_data):
        """解析arXiv API返回的XML响应"""
        try:
            # 解析XML
            root = ET.fromstring(xml_data)
            
            # 定义命名空间
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            # 查找所有条目
            entries = root.findall('.//atom:entry', namespaces)
            papers = []
            
            for entry in entries:
                # 解析基本信息
                title = entry.find('./atom:title', namespaces).text.strip()
                summary = entry.find('./atom:summary', namespaces).text.strip()
                published = entry.find('./atom:published', namespaces).text.strip()
                updated = entry.find('./atom:updated', namespaces).text.strip()
                
                # 格式化日期 (从2023-04-12T12:34:56Z 转换为 2023-04-12)
                published = published.split('T')[0] if 'T' in published else published
                updated = updated.split('T')[0] if 'T' in updated else updated
                
                # 解析作者
                authors = []
                for author in entry.findall('./atom:author', namespaces):
                    name = author.find('./atom:name', namespaces).text.strip()
                    authors.append(name)
                
                # 解析链接
                links = entry.findall('./atom:link', namespaces)
                pdf_url = None
                for link in links:
                    if link.get('title') == 'pdf' or link.get('type') == 'application/pdf':
                        pdf_url = link.get('href')
                        break
                
                # 获取arXiv ID和完整链接
                id_element = entry.find('./atom:id', namespaces)
                entry_id = id_element.text if id_element is not None else ""
                
                # 解析分类
                categories = []
                for category in entry.findall('./atom:category', namespaces):
                    term = category.get('term')
                    if term:
                        categories.append(term)
                
                # 解析arXiv特定字段
                doi = "N/A"
                journal_ref = "N/A"
                
                doi_element = entry.find('./arxiv:doi', namespaces)
                if doi_element is not None and doi_element.text:
                    doi = doi_element.text.strip()
                
                journal_ref_element = entry.find('./arxiv:journal_ref', namespaces)
                if journal_ref_element is not None and journal_ref_element.text:
                    journal_ref = journal_ref_element.text.strip()
                
                # 创建论文对象
                paper = {
                    'title': title,
                    'authors': authors,
                    'summary': summary,
                    'published': published,
                    'updated': updated,
                    'entry_id': entry_id,
                    'pdf_url': pdf_url,
                    'categories': categories,
                    'doi': doi,
                    'journal_ref': journal_ref
                }
                
                papers.append(paper)
            
            # 更新UI
            self.papers = papers
            self.table_model.set_papers(papers)
            
            # 应用当前排序
            if self.sort_combo.currentData() is not None:
                self.sort_papers()
            
            # 更新状态
            self.status_label.setText(f"找到 {len(papers)} 篇论文 (arXiv API)")
            
        except Exception as e:
            raise Exception(f"解析XML失败: {str(e)}")
    
    def search_via_server(self, keywords, search_mode, start_year, end_year, max_results):
        """通过服务器搜索论文（需要你在配置里指定自己的服务器地址）"""
        # 创建JSON请求
        request_data = {
            "keywords": keywords,
            "search_mode": search_mode,
            "max_results": max_results
        }
        
        # 添加可选参数
        if start_year:
            request_data["start_year"] = start_year
        
        if end_year:
            request_data["end_year"] = end_year
        
        # 转换为JSON
        json_data = json.dumps(request_data).encode()
        
        # 发送请求
        reply = self.network_manager.post(self.create_request("/search"), json_data)
        reply.finished.connect(lambda: self.handle_search_reply(reply))
    
    def handle_search_reply(self, reply):
        """处理搜索请求的响应"""
        self.search_button.setEnabled(True)
        
        if reply.error() == QNetworkReply.NoError:
            # 解析响应
            data = reply.readAll().data()
            self.display_results(data)
        else:
            # 处理错误
            self.handle_network_error(reply.error())
        
        # 释放资源
        reply.deleteLater()
    
    def display_results(self, data):
        """显示搜索结果"""
        try:
            # 解析JSON响应
            response = json.loads(data.decode())
            
            if not response.get("success", False):
                QMessageBox.warning(self, "搜索错误", 
                                  "错误: " + response.get("error", "未知错误"))
                self.status_label.setText("搜索失败")
                return
            
            # 处理论文列表
            papers_data = response.get("papers", [])
            self.papers = papers_data
            
            # 更新表格模型
            self.table_model.set_papers(papers_data)
            
            # 应用当前排序
            if self.sort_combo.currentData() is not None:
                self.sort_papers()
            
            # 更新状态
            network_type = "本地" if self.use_local_network else "外部"
            self.status_label.setText(f"找到 {len(papers_data)} 篇论文 ({network_type}网络)")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"解析响应时出错: {str(e)}")
            self.status_label.setText("解析响应失败")
    
    def handle_network_error(self, error):
        """处理网络错误"""
        error_message = f"网络错误: {error}"
        QMessageBox.critical(self, "网络错误", error_message)
        
        # 提示可能需要进行网络测试
        reply = QMessageBox.question(
            self, 
            "网络故障诊断", 
            "要进行网络连接测试以诊断问题吗?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.open_network_test()
            
        self.status_label.setText("网络错误")

    def download_selected(self):
        """下载选中的论文"""
        # 获取选中的论文
        selection_model = self.results_table.selectionModel()
        selected_papers = self.table_model.get_selected_papers(selection_model)
        
        if not selected_papers:
            QMessageBox.information(self, "提示", "请先选择要下载的论文")
            return
        
        # 选择保存目录
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存目录", os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )
        
        if not dir_path:
            return
        
        # 创建下载进度对话框
        progress = QProgressDialog("正在下载论文...", "取消", 0, len(selected_papers), self)
        progress.setWindowTitle("下载进度")
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        # 根据模式选择下载方法
        if self.use_direct_arxiv:
            self.status_label.setText("正在直接从arXiv下载...")
            self.download_from_arxiv(selected_papers, dir_path, progress)
        else:
            network_type = "本地" if self.use_local_network else "外部"
            self.status_label.setText(f"正在通过{network_type}网络下载...")
            self.download_via_server(selected_papers, dir_path, progress)
    
    def download_from_arxiv(self, selected_papers, dir_path, progress):
        """直接从arXiv下载论文"""
        completed = 0
        
        for i, paper in enumerate(selected_papers):
            if progress.wasCanceled():
                break
            
            # 更新进度对话框
            progress.setValue(i)
            paper_title = paper.get("title", "论文")
            progress.setLabelText(f"正在下载 ({i+1}/{len(selected_papers)}): {paper_title}")
            QApplication.processEvents()
            
            # 获取PDF URL
            pdf_url = paper.get("pdf_url")
            if not pdf_url:
                continue
            
            # 从entry_id提取arxiv ID
            entry_id = paper.get("entry_id", "")
            if "/" in entry_id:
                paper_id = entry_id.split("/")[-1]
            else:
                paper_id = entry_id
            
            # 创建安全的文件名（只保留部分常见字符）
            safe_title = "".join(
                [c if c.isalnum() or c in ['-', '_', '.', ' '] else '_' for c in paper_title]
            )
            safe_title = safe_title[:50]  # 限制文件名长度
            filename = f"{paper_id}_{safe_title}.pdf"
            filepath = os.path.join(dir_path, filename)
            
            try:
                # 发送请求下载PDF
                request = QNetworkRequest(QUrl(pdf_url))
                reply = self.network_manager.get(request)
                
                # 使用事件循环等待下载完成
                loop = QTimer()
                loop.timeout.connect(QApplication.processEvents)
                loop.start(100)
                
                while not reply.isFinished():
                    QApplication.processEvents()
                    if progress.wasCanceled():
                        reply.abort()
                        break
                
                loop.stop()
                
                # 保存文件
                if reply.error() == QNetworkReply.NoError and not progress.wasCanceled():
                    with open(filepath, "wb") as f:
                        f.write(reply.readAll().data())
                    completed += 1
                
                reply.deleteLater()
                
            except Exception as e:
                print(f"下载错误: {str(e)}")
        
        progress.setValue(len(selected_papers))
        
        # 显示完成信息
        if completed > 0:
            QMessageBox.information(
                self, "下载完成", 
                f"成功下载了 {completed} 篇论文到 {dir_path}"
            )
        else:
            QMessageBox.warning(
                self, "下载失败", 
                "没有论文被成功下载，请检查网络连接"
            )
        
        self.status_label.setText(f"已下载 {completed} 篇论文")

    def download_via_server(self, selected_papers, dir_path, progress):
        """
        通过服务器下载选中的论文。
        如果需要，可在前面 ConfigDialog 或 load_config 方法中配置自己的服务器 URL / 端口 / API Key。
        """
        completed = 0
        
        for i, paper in enumerate(selected_papers):
            if progress.wasCanceled():
                break
            
            # 从entry_id提取arxiv ID
            entry_id = paper.get("entry_id", "")
            if "/" in entry_id:
                paper_id = entry_id.split("/")[-1]
            else:
                paper_id = entry_id
                
            paper_title = paper.get("title", "paper")
            
            # 更新进度对话框
            progress.setValue(i)
            progress.setLabelText(f"正在下载 ({i+1}/{len(selected_papers)}): {paper_title}")
            QApplication.processEvents()
            
            # 准备下载请求
            request_data = {
                "paper_id": paper_id,
                "paper_title": paper_title
            }
            
            json_data = json.dumps(request_data).encode()
            
            # 发送请求到服务端 /download 端点
            # （如果你有自定义下载接口，请在此处修改为对应的路由）
            reply = self.network_manager.post(self.create_request("/download"), json_data)
            
            # 使用“阻塞式”轮询等待本次下载请求完成
            loop = QTimer()
            loop.timeout.connect(QApplication.processEvents)
            loop.start(100)
            
            while not reply.isFinished():
                QApplication.processEvents()
                if progress.wasCanceled():
                    reply.abort()
                    break
            
            loop.stop()
            
            # 处理响应
            if reply.error() == QNetworkReply.NoError and not progress.wasCanceled():
                response_data = json.loads(bytes(reply.readAll()).decode())
                
                if response_data.get("success"):
                    # 获取下载链接
                    download_link = response_data.get("download_link")
                    
                    if download_link:
                        # 再次向服务器请求 PDF 文件
                        file_request = self.create_request(download_link)
                        file_reply = self.network_manager.get(file_request)
                        
                        # 等待文件下载完成
                        loop = QTimer()
                        loop.timeout.connect(QApplication.processEvents)
                        loop.start(100)
                        
                        while not file_reply.isFinished():
                            QApplication.processEvents()
                            if progress.wasCanceled():
                                file_reply.abort()
                                break
                        
                        loop.stop()
                        
                        # 保存文件
                        if file_reply.error() == QNetworkReply.NoError and not progress.wasCanceled():
                            filename = download_link.split("/")[-1]
                            filepath = os.path.join(dir_path, filename)
                            
                            with open(filepath, "wb") as f:
                                f.write(file_reply.readAll().data())
                            
                            completed += 1
                        
                        file_reply.deleteLater()
                
            reply.deleteLater()
        
        progress.setValue(len(selected_papers))
        
        # 显示完成信息
        if completed > 0:
            QMessageBox.information(
                self, "下载完成", 
                f"成功下载了 {completed} 篇论文到 {dir_path}"
            )
        else:
            QMessageBox.warning(
                self, "下载失败", 
                "没有论文被成功下载，请检查服务器设置和网络连接"
            )
        
        self.status_label.setText(f"已下载 {completed} 篇论文")

    def save_to_csv(self):
        """保存结果为CSV文件"""
        if not self.papers:
            QMessageBox.information(self, "提示", "没有可保存的结果")
            return
        
        # 选择保存文件
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存CSV文件", 
            os.path.join(os.path.expanduser("~"), "arxiv_papers.csv"),
            "CSV文件 (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            # 打开文件
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                
                # 写入标题行
                writer.writerow([
                    "序号", "标题", "作者", "发布日期", "更新日期", "类别", 
                    "DOI", "期刊引用", "摘要", "arXiv链接", "PDF链接"
                ])
                
                # 写入数据
                for i, paper in enumerate(self.papers, 1):
                    authors = ", ".join(paper.get("authors", []))
                    categories = ", ".join(paper.get("categories", []))
                    
                    writer.writerow([
                        i,
                        paper.get("title", ""),
                        authors,
                        paper.get("published", ""),
                        paper.get("updated", ""),
                        categories,
                        paper.get("doi", "N/A"),
                        paper.get("journal_ref", "N/A"),
                        paper.get("summary", "").replace("\n", " "),
                        paper.get("entry_id", ""),
                        paper.get("pdf_url", "")
                    ])
            
            self.status_label.setText(f"已保存CSV到: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存文件时出错: {str(e)}")

    def save_to_text(self):
        """保存结果为文本文件"""
        if not self.papers:
            QMessageBox.information(self, "提示", "没有可保存的结果")
            return
        
        # 选择保存文件
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存文本文件", 
            os.path.join(os.path.expanduser("~"), "arxiv_papers.txt"),
            "文本文件 (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"找到 {len(self.papers)} 篇匹配的论文:\n\n")
                
                for i, paper in enumerate(self.papers, 1):
                    authors = ", ".join(paper.get("authors", []))
                    categories = ", ".join(paper.get("categories", []))
                    
                    f.write(f"{i}. 标题: {paper.get('title', '')}\n")
                    f.write(f"   作者: {authors}\n")
                    f.write(f"   发布日期: {paper.get('published', '')}\n")
                    f.write(f"   更新日期: {paper.get('updated', '')}\n")
                    f.write(f"   类别: {categories}\n")
                    
                    if paper.get("doi") != "N/A":
                        f.write(f"   DOI: {paper.get('doi', '')}\n")
                    
                    if paper.get("journal_ref") != "N/A":
                        f.write(f"   期刊引用: {paper.get('journal_ref', '')}\n")
                    
                    f.write(f"   摘要: {paper.get('summary', '')}\n")
                    f.write(f"   arXiv链接: {paper.get('entry_id', '')}\n")
                    f.write(f"   PDF链接: {paper.get('pdf_url', '')}\n")
                    f.write("-" * 80 + "\n")
            
            self.status_label.setText(f"已保存文本到: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存文件时出错: {str(e)}")

    def open_settings(self):
        """
        打开设置对话框。
        如需配置自己的服务器，请在对话框中输入：
        1. 服务器URL
        2. 对应API密钥
        还可以切换“直接访问arXiv”和“服务器模式”。
        """
        dialog = ConfigDialog(self)
        
        # 设置当前模式及本地/外部网络初始值
        dialog.direct_arxiv_radio.setChecked(self.use_direct_arxiv)
        dialog.server_radio.setChecked(not self.use_direct_arxiv)
        dialog.local_network_radio.setChecked(self.use_local_network)
        dialog.external_network_radio.setChecked(not self.use_local_network)
        dialog.local_server_url_edit.setText(self.local_server_url)
        dialog.local_api_key_edit.setText(self.local_api_key)
        dialog.external_server_url_edit.setText(self.external_server_url)
        dialog.external_api_key_edit.setText(self.external_api_key)
        
        if dialog.exec_() == QDialog.Accepted:
            old_direct_arxiv = self.use_direct_arxiv
            old_local_network = self.use_local_network
            
            # 更新主窗口状态
            self.use_direct_arxiv = dialog.use_direct_arxiv()
            self.use_local_network = dialog.use_local_network()
            self.local_server_url = dialog.local_server_url_edit.text()
            self.local_api_key = dialog.local_api_key_edit.text()
            self.external_server_url = dialog.external_server_url_edit.text()
            self.external_api_key = dialog.external_api_key_edit.text()
            
            # 设置当前活动的服务器
            self.server_url = dialog.get_active_server_url()
            self.api_key = dialog.get_active_api_key()
            
            # 更新UI显示
            self.mode_value.setText("直接访问arXiv" if self.use_direct_arxiv else "服务器模式")
            self.server_value.setText("本地网络" if self.use_local_network else "外部网络")
            self.server_url_label.setText(f"服务器: {self.server_url}")
            
            # 显示/隐藏网络环境控件
            self.server_label.setVisible(not self.use_direct_arxiv)
            self.server_value.setVisible(not self.use_direct_arxiv)
            self.network_menu.setEnabled(not self.use_direct_arxiv)
            
            # 更新菜单选中状态
            self.direct_arxiv_action.setChecked(self.use_direct_arxiv)
            self.server_action.setChecked(not self.use_direct_arxiv)
            self.use_local_action.setChecked(self.use_local_network)
            self.use_external_action.setChecked(not self.use_local_network)
            
            # 显示变更信息
            if old_direct_arxiv != self.use_direct_arxiv:
                self.status_label.setText(f"已切换到{'直接访问arXiv' if self.use_direct_arxiv else '服务器'}模式")
            elif not self.use_direct_arxiv and old_local_network != self.use_local_network:
                self.status_label.setText(f"已切换到{'本地' if self.use_local_network else '外部'}网络环境")
            else:
                self.status_label.setText("配置已更新")

    def open_network_test(self):
        """
        打开网络测试对话框。
        在这里可以：
        1. 测试Ping
        2. 测试 API 连接
        并可将测试通过的服务器配置“应用”到主程序中。
        """
        network_test = NetworkTestDialog(self)
        network_test.server_url_edit.setText(self.server_url)
        network_test.api_key_edit.setText(self.api_key)
        
        # 如果测试成功并用户选择使用该配置
        if network_test.exec_() == QDialog.Accepted:
            new_url = network_test.get_server_url()
            new_key = network_test.get_api_key()
            
            # 检查是否有变更
            if new_url != self.server_url or new_key != self.api_key:
                self.server_url = new_url
                self.api_key = new_key
                
                # 更新显示
                self.server_url_label.setText(f"服务器: {self.server_url}")
                
                # 根据当前模式保存设置
                if not self.use_direct_arxiv:
                    if self.use_local_network:
                        self.local_server_url = new_url
                        self.local_api_key = new_key
                    else:
                        self.external_server_url = new_url
                        self.external_api_key = new_key
                
                # 保存新配置
                settings = QSettings("arXivSearchClient", "Config")
                settings.setValue("serverUrl", self.server_url)
                settings.setValue("apiKey", self.api_key)
                
                if not self.use_direct_arxiv:
                    if self.use_local_network:
                        settings.setValue("localServerUrl", self.local_server_url)
                        settings.setValue("localApiKey", self.local_api_key)
                    else:
                        settings.setValue("externalServerUrl", self.external_server_url)
                        settings.setValue("externalApiKey", self.external_api_key)
                
                self.status_label.setText("已更新网络配置")

    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, 
            "关于（！本代码完全免费！）", 
            "arXiv论文搜索工具\n版本 1.2.0\n\n"
            "该工具可以搜索arXiv上的论文并下载PDF。\n"
            "1.支持直接访问arXiv API或使用自建服务器。\n"
            "2.服务器模式下支持本地网络和外部网络环境切换。\n"
            "3.可以按标题和发布日期排序。"
        )


# 程序入口
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("arXiv论文搜索工具")
    app.setApplicationVersion("1.2.0")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

           
