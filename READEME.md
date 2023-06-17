## plugin_mj
这个项目是[chatgpt-on-wechat](https://github.com/zhayujie/chatgpt-on-wechat) 集成midjourney 的插件, 实现以下功能：
- [x] 根据prompt 绘制图片
- [x] Ux 使用图片
- [x] Vx 变换图片

### 使用方式
#### 插件集成
1. 把项目解压到chatgpt-on-wechat/plugins/plugin_mj/ 目录下
2. 配置 chatgpt-on-wechat/plugins/plugins.json
 ```json
{
  "Midjourney": {
    "enabled": true,
    "priority": 0
  }
}
```
3. 配置 plugin_mj/config.json 修改 base_url 为你的midjourney-proxy 地址
4. 重启chatgpt-on-wechat

