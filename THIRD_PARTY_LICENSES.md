# Third-Party Licenses & Credits

本文件列出 CrEventor 所使用、依赖或衍生自的第三方项目，以及它们的许可证与致谢信息。

---

## Credits

### Based on

CrEventor 基于以下项目衍生开发：

- [leoetlino/event-editor](https://github.com/leoetlino/event-editor) — GNU GPL v2 或更高版本
- [leoetlino/evfl](https://github.com/leoetlino/evfl) — GNU GPL v2 或更高版本

### Third-party libraries

#### Python 依赖

| 库 | 版本 | 许可证 | 主页 / 仓库 |
|---|---|---|---|
| PyQt5 | 5.15.11 | GPL v3（或商业授权） | https://www.riverbankcomputing.com/software/pyqt/ |
| PyQtWebEngine | 5.15.7 | GPL v3（或商业授权） | https://www.riverbankcomputing.com/software/pyqtwebengine/ |
| aamp | 1.4.1.post1 | GPL v2+ | https://github.com/leoetlino/aamp |
| byml | 2.4.5.post1 | GPL v2+ | https://github.com/leoetlino/byml-v2 |
| rstb | 1.2.2 | GPL v2+ | https://github.com/leoetlino/rstb |
| oead | 1.2.9.post4 | GPL v2+ | https://github.com/zeldamods/oead |
| PyYAML | 6.0.3 | MIT | https://pyyaml.org/ |
| msgpack | 1.2.1 | Apache-2.0 | https://msgpack.org/ |
| Pillow | 12.3.0 | MIT-CMU | https://python-pillow.org/ |
| sortedcontainers | 2.4.0 | Apache-2.0 | http://www.grantjenks.com/docs/sortedcontainers/ |

#### 前端依赖

| 库 | 许可证 | 主页 / 仓库 |
|---|---|---|
| ProseMirror | MIT | https://prosemirror.net/ |
| d3 | BSD-3-Clause | https://d3js.org/ |
| dagre-d3 | MIT | https://github.com/dagrejs/dagre-d3 |
| graphlib | BSD-3-Clause | https://github.com/dagrejs/graphlib |
| d3-context-menu | MIT | https://github.com/patorjk/d3-context-menu |
| lodash | MIT | https://lodash.com/ |

### Community resources

- [ZeldaMods Wiki](https://zeldamods.org/) — Mod 制作文档与规范

---

## Licenses

### GNU General Public License v2 或更高版本（GPL v2+）

以下项目采用 GPL v2 或更高版本授权，与 CrEventor 整体许可证一致：

- leoetlino/event-editor
- leoetlino/evfl
- leoetlino/aamp
- leoetlino/byml-v2
- leoetlino/rstb
- zeldamods/oead

完整许可证文本见项目根目录的 [LICENSE](./LICENSE)。

### GNU General Public License v3（GPL v3）

- PyQt5（Copyright © Riverbank Computing Limited）
- PyQtWebEngine（Copyright © Riverbank Computing Limited）

完整许可证文本见 <https://www.gnu.org/licenses/gpl-3.0.html>。

### MIT License

适用于：

- **ProseMirror** — Copyright © 2015-2023 Marijn Haverbeke
- **PyYAML** — Copyright © 2006-2016 Kirill Simonov；Copyright © 2017-2021 Ingy döt Net
- **dagre-d3** — Copyright © 2012-2013 Chris Pettitt
- **d3-context-menu** — Copyright © Patrick Gillespie
- **lodash** — Copyright JS Foundation and other contributors（内嵌于 dagre-d3 / graphlib 打包产物）

```
MIT License

Copyright (c) 上列各库的版权所有者

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### BSD 3-Clause License

适用于：

- **d3** (v3.5.17) — Copyright (c) 2010-2016 Michael Bostock
- **graphlib** (v2.1.5) — Copyright (c) 2014 Chris Pettitt

```
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### Apache License 2.0

适用于：

- **msgpack**（msgpack-python）
- **sortedcontainers**（Copyright © Grant Jenks）

完整许可证文本见 <https://www.apache.org/licenses/LICENSE-2.0>。

### MIT-CMU

适用于：

- **Pillow**（PIL 的分支）

完整许可证文本见 <https://raw.githubusercontent.com/python-pillow/Pillow/main/LICENSE>。
