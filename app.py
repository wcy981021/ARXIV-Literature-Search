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
