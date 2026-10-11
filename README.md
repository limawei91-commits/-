# 手掌地球仪 🌍🖐️

用摄像头识别手势，在空中操控一个 3D 地球。单个 `index.html` 文件，无需构建。

## 运行

摄像头只能在 `https://` 或 `localhost` 下使用，所以请用本地服务器打开：

```bash
python3 -m http.server 8000
# 浏览器访问 http://localhost:8000
```

点击左上角「开启摄像头手势控制」，允许摄像头权限即可。

## 手势

| 手势 | 作用 |
| --- | --- |
| 🖐️ 张开手掌并移动 | 旋转地球（松开后带惯性） |
| ✊ 握拳 | 定住地球 |
| 🤏 拇指食指捏合 + 上下移动 | 缩放（向上放大，向下缩小） |
| 🙌 双手张开 / 靠拢 | 缩放 |
| ☝️ 只竖食指 | 开关自转 |

没开摄像头时，也可以用鼠标拖拽旋转、滚轮缩放，手机上可以手指拖动。

## 技术

- [Three.js](https://threejs.org/) 渲染地球、大气辉光和星空
- [MediaPipe Hand Landmarker](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker) 在浏览器本地识别 21 个手部关键点，视频不会上传
- 地球贴图来自 [three-globe](https://github.com/vasturiano/three-globe) 示例素材（NASA Blue Marble）
