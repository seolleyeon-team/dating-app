import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/shop/services/heart_purchase_gateway.dart';

void main() {
  test('Apple app account token is deterministic and UUID-shaped', () {
    expect(
      appleAppAccountTokenForUserId('kakao-user-123'),
      '1332de1d-bae0-58c7-9a81-07f09564dc75',
    );
    expect(
      appleAppAccountTokenForUserId('kakao-user-123'),
      appleAppAccountTokenForUserId('kakao-user-123'),
    );
    expect(
      appleAppAccountTokenForUserId('kakao-user-123'),
      matches(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ),
      ),
    );
  });
}
