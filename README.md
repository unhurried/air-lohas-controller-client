# air-lohas-controller-client

パナソニックホームズの全館空調システム「エアロハス」の制御プログラム。ホームネットワーク経由でエアロハス本体と通信し、温度設定等を制御する。ネットワーク接続機能を持ちMicroPythonを実行できるSBCで動作する。

温度設定は[air-lohas-controller-server](https://github.com/unhurried/air-lohas-controller-server)からCloudflare Workers KVに書き込まれた情報を参照する。

## 注意事項

エアロハスは本プロジェクトのような使い方を正式にサポートしていないため、試す場合は自己責任で行うこと。また、エアロハス本体との通信方式は公開されていないため、具体的な通信ロジックはスケルトンコードとしている。
