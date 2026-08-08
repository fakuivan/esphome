#include "subscribe_state.h"
#ifdef USE_API
#include "api_connection.h"
#include "esphome/core/log.h"

namespace esphome::api {

#ifdef USE_DEVICES
bool InitialStateIterator::on_begin() {
  const auto &devices = App.get_devices();
  if (this->at_ >= devices.size())
    return true;
  if (!this->client_->send_device_state(devices[this->at_]))
    return false;
  return ++this->at_ >= devices.size();
}
#endif

// Generate entity handler implementations using macros
#ifdef USE_BINARY_SENSOR
INITIAL_STATE_HANDLER(binary_sensor, binary_sensor::BinarySensor, BINARY_SENSOR)
#endif
#ifdef USE_COVER
INITIAL_STATE_HANDLER(cover, cover::Cover, COVER)
#endif
#ifdef USE_FAN
INITIAL_STATE_HANDLER(fan, fan::Fan, FAN)
#endif
#ifdef USE_LIGHT
INITIAL_STATE_HANDLER(light, light::LightState, LIGHT)
#endif
#ifdef USE_SENSOR
INITIAL_STATE_HANDLER(sensor, sensor::Sensor, SENSOR)
#endif
#ifdef USE_SWITCH
INITIAL_STATE_HANDLER(switch, switch_::Switch, SWITCH)
#endif
#ifdef USE_TEXT_SENSOR
INITIAL_STATE_HANDLER(text_sensor, text_sensor::TextSensor, TEXT_SENSOR)
#endif
#ifdef USE_CLIMATE
INITIAL_STATE_HANDLER(climate, climate::Climate, CLIMATE)
#endif
#ifdef USE_NUMBER
INITIAL_STATE_HANDLER(number, number::Number, NUMBER)
#endif
#ifdef USE_DATETIME_DATE
INITIAL_STATE_HANDLER(date, datetime::DateEntity, DATETIME_DATE)
#endif
#ifdef USE_DATETIME_TIME
INITIAL_STATE_HANDLER(time, datetime::TimeEntity, DATETIME_TIME)
#endif
#ifdef USE_DATETIME_DATETIME
INITIAL_STATE_HANDLER(datetime, datetime::DateTimeEntity, DATETIME_DATETIME)
#endif
#ifdef USE_TEXT
INITIAL_STATE_HANDLER(text, text::Text, TEXT)
#endif
#ifdef USE_SELECT
INITIAL_STATE_HANDLER(select, select::Select, SELECT)
#endif
#ifdef USE_LOCK
INITIAL_STATE_HANDLER(lock, lock::Lock, LOCK)
#endif
#ifdef USE_VALVE
INITIAL_STATE_HANDLER(valve, valve::Valve, VALVE)
#endif
#ifdef USE_MEDIA_PLAYER
INITIAL_STATE_HANDLER(media_player, media_player::MediaPlayer, MEDIA_PLAYER)
#endif
#ifdef USE_ALARM_CONTROL_PANEL
INITIAL_STATE_HANDLER(alarm_control_panel, alarm_control_panel::AlarmControlPanel, ALARM_CONTROL_PANEL)
#endif
#ifdef USE_WATER_HEATER
INITIAL_STATE_HANDLER(water_heater, water_heater::WaterHeater, WATER_HEATER)
#endif
#ifdef USE_UPDATE
INITIAL_STATE_HANDLER(update, update::UpdateEntity, UPDATE)
#endif

// Generate handlers for stateless entity types.
// NOLINTBEGIN(bugprone-macro-parentheses)
#define ENTITY_TYPE_(type, singular, plural, count, upper) \
  bool InitialStateIterator::on_##singular(type *entity) { \
    return entity->is_available() || \
           this->client_->send_entity_availability_state(entity, enums::ENTITY_TYPE_##upper); \
  }
#define ENTITY_CONTROLLER_TYPE_(type, singular, plural, count, upper, callback)
#include "esphome/core/entity_types.h"
#undef ENTITY_TYPE_
#undef ENTITY_CONTROLLER_TYPE_
// NOLINTEND(bugprone-macro-parentheses)

// Event is an ENTITY_CONTROLLER_TYPE_ but has no state to send.
#ifdef USE_EVENT
bool InitialStateIterator::on_event(event::Event *entity) {
  return entity->is_available() || this->client_->send_entity_availability_state(entity, enums::ENTITY_TYPE_EVENT);
}
#endif

#ifdef USE_CAMERA
bool InitialStateIterator::on_camera(camera::Camera *camera) {
  return camera->is_available() || this->client_->send_entity_availability_state(camera, enums::ENTITY_TYPE_CAMERA);
}
#endif

InitialStateIterator::InitialStateIterator(APIConnection *client) : client_(client) {}

}  // namespace esphome::api
#endif
