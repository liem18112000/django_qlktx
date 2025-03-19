(function($) {
    if (typeof django !== "undefined" && django.jQuery) {
        $ = django.jQuery;  // ✅ Use Django’s jQuery if available
    } else if (typeof $ === "undefined") {
        console.error("jQuery is not loaded!");
        return;
    }

    $(document).ready(function() {
        console.log("Custom admin action script loaded!");  // ✅ Debugging

        function updateFloorOptions(buildingSelector, floorSelector) {
            $(buildingSelector).change(function() {
                var buildingId = $(this).val();
                var floorSelect = $(floorSelector);

                if (!buildingId) {
                    floorSelect.html('<option value="">---------</option>');
                    return;
                }

                $.ajax({
                    url: '/admin/get_floors/',  // ✅ Ensure the correct URL
                    data: { building_id: buildingId },
                    success: function(data) {
                        floorSelect.html('');
                        $.each(data.floors, function(index, floor) {
                            floorSelect.append(
                                $('<option></option>').attr('value', floor.id).text("Tầng " + floor.floor_number)  // ✅ Corrected!
                            );
                        });
                    },
                    error: function(xhr, status, error) {
                        console.error("Error fetching floors:", error);
                        floorSelect.html('<option value="">Error loading floors</option>');
                    }
                });
            });
        }

        // Bind change event to all building-floor pairs
        updateFloorOptions('#id_building', '#id_floor');
        updateFloorOptions('#id_building_1', '#id_floor_1');
        updateFloorOptions('#id_building_2', '#id_floor_2');
    });

})(window.jQuery || django?.jQuery || $);  // ✅ Use global jQuery if Django's jQuery is missing
