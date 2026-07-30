
import 'package:flutter/widgets.dart';

Widget buildLeakyPhoto(List<String> photoUrls) {
  return Image.network(photoUrls.first);
}
