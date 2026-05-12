<script setup lang="ts">
import { onLaunch, onShow, onHide } from "@dcloudio/uni-app";
import { checkSmartScaleAppUpdate } from "./utils/appUpdate";

onLaunch(() => {
  void checkSmartScaleAppUpdate();
});
onShow(() => {
  console.log("App Show");
});
onHide(() => {
  console.log("App Hide");
});
</script>
<style></style>
