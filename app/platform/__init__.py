"""平台接入层：业务层通过平台无关网关读写店铺数据，不直接感知具体电商平台。

- MockShopGateway / MockCampaignPublisher：默认实现，数据来自本地合成业务表；
- TaobaoShopGateway / TaobaoCampaignPublisher：淘宝开放平台（TOP）协议映射骨架，
  默认不含网络 transport，只支持注入 fake transport 验证签名、参数和响应映射；
- factory.get_shop_gateway() / factory.get_campaign_publisher()：按配置返回实现。
"""
